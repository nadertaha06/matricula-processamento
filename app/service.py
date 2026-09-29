from datetime import datetime, timezone
from sqlalchemy import select
from app.config import get_settings
from app.events import emit
from app.models import Lote, Avaliacao
from app.strategies import CriterioDesempateFactory, faltam_pre_requisitos
from app.clients import ServicosAcademicos


def criterio(session, turma_id):
    lote = session.get(Lote, turma_id)
    if lote is None:
        nome = get_settings().criterio_desempate
        CriterioDesempateFactory.criar(nome)
        lote = Lote(turma_id=turma_id, criterio=nome)
        session.add(lote)
        session.flush()
    return CriterioDesempateFactory.criar(lote.criterio)


def lista_espera(session, turma_id):
    estrategia = criterio(session, turma_id)
    candidatos = [a.candidato for a in session.scalars(select(Avaliacao).where(Avaliacao.turma_id == turma_id, Avaliacao.resultado == 'EM_ESPERA'))]
    return [{'posicao':i, **c} for i,c in enumerate(estrategia.ordenar(candidatos), start=1)]


def avaliar(session, candidato, servicos, permitir_reserva=True):
    sid = candidato['solicitacao_id']
    solicitacao = servicos.solicitacao(sid)
    if solicitacao['aluno_id'] != candidato['aluno_id'] or solicitacao['turma_id'] != candidato['turma_id']:
        raise ValueError('Evento diverge da solicitacao')
    avaliacao = session.get(Avaliacao, sid)
    if solicitacao['status'] == 'CANCELADA':
        if avaliacao:
            avaliacao.resultado = 'CANCELADA'
        return 'CANCELADA'
    if avaliacao and avaliacao.resultado in {'DEFERIDA', 'INDEFERIDA', 'CANCELADA'}:
        return avaliacao.resultado
    turma = servicos.turma(candidato['turma_id'])
    if turma is None:
        resultado, motivo = 'INDEFERIDA', 'TURMA_INEXISTENTE'
    elif faltam_pre_requisitos(turma['pre_requisitos'], servicos.historico(candidato['aluno_id'])['disciplinas']):
        resultado, motivo = 'INDEFERIDA', 'PRE_REQUISITO'
    elif not permitir_reserva:
        resultado, motivo = 'EM_ESPERA', 'AGUARDANDO_VAGA'
    else:
        motivo = servicos.reservar(candidato)
        resultado = 'DEFERIDA' if motivo is None else ('EM_ESPERA' if motivo == 'SEM_VAGAS' else 'INDEFERIDA')
    if avaliacao is None:
        avaliacao = Avaliacao(solicitacao_id=sid, turma_id=candidato['turma_id'], candidato=candidato, resultado=resultado, revisao=0)
        session.add(avaliacao)
    elif avaliacao.resultado == resultado and avaliacao.motivo == motivo:
        return resultado
    avaliacao.resultado, avaliacao.motivo = resultado, motivo
    avaliacao.revisao += 1
    emit(session, 'matricula.avaliada', {'solicitacao_id':sid, 'resultado':resultado, 'motivo':motivo,
        'revisao':avaliacao.revisao, 'avaliado_em':datetime.now(timezone.utc).isoformat()})
    session.flush()
    return resultado


def promover(session, turma_id, servicos):
    candidatos = lista_espera(session, turma_id)
    if not candidatos:
        return
    # One candidate per transaction: a later HTTP failure cannot roll back a seat already granted.
    resultado = avaliar(session, candidatos[0], servicos)
    if resultado != 'EM_ESPERA':
        emit(session, 'lista.reavaliar', {'turma_id': turma_id})


def process_event(session, topic, payload, servicos):
    if topic == 'matricula.solicitada':
        # Validate all ordering fields before storing a wait-list entry.
        candidato = {k:payload[k] for k in ('solicitacao_id','aluno_id','turma_id','coeficiente','periodo_aluno','solicitado_em')}
        CriterioDesempateFactory.criar('coeficiente').chave(candidato)
        datetime.fromisoformat(candidato['solicitado_em'])
        criterio(session, candidato['turma_id'])
        outros = [c for c in lista_espera(session, candidato['turma_id']) if c['solicitacao_id'] != candidato['solicitacao_id']]
        avaliar(session, candidato, servicos, permitir_reserva=not outros)
        if outros:
            emit(session, 'lista.reavaliar', {'turma_id': candidato['turma_id']})
    elif topic == 'matricula.cancelada':
        s = servicos.solicitacao(payload['solicitacao_id'])
        if s['status'] != 'CANCELADA' or s['turma_id'] != payload['turma_id']:
            raise ValueError('Cancelamento nao confirmado pela origem')
        avaliacao = session.get(Avaliacao, payload['solicitacao_id'])
        if avaliacao:
            avaliacao.resultado = 'CANCELADA'
        servicos.liberar(payload)
    elif topic in {'vaga.liberada', 'lista.reavaliar'}:
        promover(session, payload['turma_id'], servicos)
    else:
        raise ValueError('Evento desconhecido')


def handle_event(session, topic, payload):
    servicos = ServicosAcademicos()
    try:
        process_event(session, topic, payload, servicos)
    finally:
        servicos.close()
