import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db import get_engine
from app.events import Outbox
from app.models import Avaliacao
from app.service import process_event, avaliar, promover, lista_espera

pytestmark = pytest.mark.integration


class Academico:
    """External HTTP boundary is isolated here; E2E exercises all real APIs."""
    def __init__(self):
        self.status = {}
        self.oferta = {'pre_requisitos':[]}
        self.cursadas = []
        self.motivo = None
        self.reservas = set()

    def solicitacao(self, sid):
        return {'id':sid,'status':self.status.get(sid,'SOLICITADA'),'aluno_id':sid,'turma_id':'t'}

    def turma(self, tid):
        return self.oferta

    def historico(self, aluno):
        return {'disciplinas':self.cursadas}

    def reservar(self, candidato):
        if not self.motivo:
            self.reservas.add(candidato['solicitacao_id'])
        return self.motivo

    def liberar(self, candidato):
        self.reservas.discard(candidato['solicitacao_id'])


def candidato(sid='a', coef=8, periodo=2):
    return {'solicitacao_id':sid,'aluno_id':sid,'turma_id':'t','coeficiente':coef,'periodo_aluno':periodo,'solicitado_em':'2026-09-01T10:00:00+00:00'}


def executar(c, api):
    with Session(get_engine()) as s, s.begin():
        process_event(s, 'matricula.solicitada', c, api)


@pytest.mark.parametrize('motivo,resultado', [(None,'DEFERIDA'),('SEM_VAGAS','EM_ESPERA'),('CHOQUE_HORARIO','INDEFERIDA'),('DISCIPLINA_JA_MATRICULADA','INDEFERIDA')])
def test_resultado_persistido(client, motivo, resultado):
    api = Academico()
    api.motivo = motivo
    executar(candidato(), api)
    r = client.get('/avaliacoes/a').json()
    assert r['resultado'] == resultado
    assert r['motivo'] == motivo
    executar(candidato(), api)
    with Session(get_engine()) as s:
        events = list(s.scalars(select(Outbox)))
        assert len(events) == 1
        assert events[0].payload['resultado'] == resultado
        assert events[0].payload['revisao'] == 1


def test_pre_requisito_e_turma_ausente(client):
    api = Academico()
    api.oferta = {'pre_requisitos':['CAL1']}
    executar(candidato('a'), api)
    assert client.get('/avaliacoes/a').json()['motivo'] == 'PRE_REQUISITO'
    api.oferta = None
    executar(candidato('b'),api)
    assert client.get('/avaliacoes/b').json()['motivo'] == 'TURMA_INEXISTENTE'
    assert api.reservas == set()


def test_promocao_respeita_criterio_e_cancela_espera(client):
    api = Academico()
    api.motivo = 'SEM_VAGAS'
    executar(candidato('a',coef=7,periodo=5),api)
    executar(candidato('b',coef=9,periodo=2),api)
    executar(candidato('c',coef=8,periodo=3),api)
    assert [x['solicitacao_id'] for x in client.get('/turmas/t/lista-espera').json()] == ['b','c','a']
    assert client.put('/turmas/t/criterio',json={'criterio':'periodo'}).status_code == 200
    assert [x['solicitacao_id'] for x in client.get('/turmas/t/lista-espera').json()] == ['a','c','b']
    api.status['a'] = 'CANCELADA'
    with Session(get_engine()) as s, s.begin():
        promover(s,'t',api)  # canceled first; next still sees a full class
    assert client.get('/avaliacoes/a').json()['resultado'] == 'CANCELADA'
    api.motivo = None
    with Session(get_engine()) as s, s.begin():
        process_event(s,'vaga.liberada',{'turma_id':'t'},api)
    with Session(get_engine()) as s, s.begin():
        process_event(s,'lista.reavaliar',{'turma_id':'t'},api)
    assert client.get('/turmas/t/lista-espera').json() == []
    assert api.reservas == {'b','c'}
    assert client.get('/avaliacoes/b').json()['revisao'] == 2


def test_cancelamento_devolve_reserva_e_e_idempotente(client):
    api=Academico()
    executar(candidato(),api)
    api.status['a']='CANCELADA'
    with Session(get_engine()) as s, s.begin():
        process_event(s,'matricula.cancelada',candidato(),api)
    assert api.reservas == set()
    assert client.get('/avaliacoes/a').json()['resultado'] == 'CANCELADA'
    executar(candidato(),api)
    api.status['b']='CANCELADA'
    executar(candidato('b'),api)
    with Session(get_engine()) as s, s.begin():
        process_event(s,'matricula.cancelada',candidato('b'),api)
    assert client.get('/avaliacoes/b').status_code == 404


def test_eventos_divergentes_e_desconhecidos():
    api=Academico()
    with Session(get_engine()) as s:
        with pytest.raises(ValueError,match='desconhecido'):
            process_event(s,'outro',{},api)
        with pytest.raises(ValueError,match='nao confirmado'):
            process_event(s,'matricula.cancelada',candidato(),api)
        with pytest.raises(ValueError,match='diverge'):
            avaliar(s,{**candidato(),'aluno_id':'falso'},api)


def test_configuracao_invalida(client):
    assert client.put('/turmas/t/criterio',json={'criterio':'invalido'}).status_code == 422
    assert client.get('/avaliacoes/ausente').status_code == 404


def test_promocao_confirma_um_candidato_sem_depender_do_seguinte(client):
    api = Academico()
    api.motivo = 'SEM_VAGAS'
    executar(candidato('a', coef=9), api)
    executar(candidato('b', coef=8), api)
    api.motivo = None
    original = api.solicitacao
    def consulta(sid):
        if sid == 'b':
            raise ConnectionError('Servico indisponivel para proximo candidato')
        return original(sid)
    api.solicitacao = consulta
    with Session(get_engine()) as s, s.begin():
        promover(s, 't', api)
    assert client.get('/avaliacoes/a').json()['resultado'] == 'DEFERIDA'
    assert api.reservas == {'a'}


def test_nova_solicitacao_nao_ultrapassa_fila_pendente(client):
    api = Academico()
    api.motivo = 'SEM_VAGAS'
    executar(candidato('a', coef=9),api)
    api.motivo = None  # seat freed, but its event hasn't arrived yet
    executar(candidato('b', coef=7),api)
    assert 'b' not in api.reservas
    assert client.get('/avaliacoes/b').json()['resultado'] == 'EM_ESPERA'
