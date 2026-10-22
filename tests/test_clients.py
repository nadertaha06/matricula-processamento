import httpx
import pytest
from prometheus_client import REGISTRY
from app.clients import ServicosAcademicos

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('method,args,status,payload,expected', [
    ('turma',['t'],200,{'id':'t'},{'id':'t'}), ('turma',['t'],404,{},None),
    ('historico',['auth0|a'],200,{'disciplinas':[]},{'disciplinas':[]}),
    ('solicitacao',['s'],200,{'status':'SOLICITADA'},{'status':'SOLICITADA'}),
    ('reservar',[{'turma_id':'t','solicitacao_id':'s','aluno_id':'a'}],200,{},None),
    ('reservar',[{'turma_id':'t','solicitacao_id':'s','aluno_id':'a'}],409,{'detail':'SEM_VAGAS'},'SEM_VAGAS'),
    ('liberar',[{'turma_id':'t','solicitacao_id':'s'}],204,{},None),
    ('liberar',[{'turma_id':'t','solicitacao_id':'s'}],404,{},None)])
def test_protocolo_http(method,args,status,payload,expected):
    client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status,json=payload)))
    servicos=ServicosAcademicos(client)
    assert getattr(servicos,method)(*args) == expected
    servicos.close()


@pytest.mark.parametrize('method,args,status,payload', [
    ('turma',['t'],503,{}),('historico',['a'],503,{}),('solicitacao',['s'],404,{}),
    ('liberar',[{'turma_id':'t','solicitacao_id':'s'}],503,{}),
    ('reservar',[{'turma_id':'t','solicitacao_id':'s','aluno_id':'a'}],409,{'detail':'SOLICITACAO_DIVERGENTE'})])
def test_falhas_http_nao_sao_transformadas_em_aprovacao(method,args,status,payload):
    servicos=ServicosAcademicos(httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status,json=payload))))
    with pytest.raises(httpx.HTTPStatusError):
        getattr(servicos,method)(*args)
    servicos.close()


def test_internal_http_uses_private_credential(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'internal_api_token', 'private-service-token')
    def endpoint(request):
        if request.headers.get('X-Service-Token') != 'private-service-token':
            return httpx.Response(401)
        return httpx.Response(200, json={'id':'t'})
    client = ServicosAcademicos(httpx.Client(transport=httpx.MockTransport(endpoint)))
    assert client.turma('t') == {'id':'t'}
    client.close()


def valor(nome, **labels):
    return REGISTRY.get_sample_value(nome, labels) or 0.0


def test_metricas_por_destino_e_status():
    def endpoint(request):
        if request.url.path.startswith('/turmas/t/reservas'):
            return httpx.Response(409 if request.method == 'POST' else 404, json={'detail':'SEM_VAGAS'})
        return httpx.Response(200, json={'id':'x', 'disciplinas':[]})
    esperado = {('disciplinas','200'):1, ('disciplinas','409'):1, ('disciplinas','404'):1, ('solicitacoes','200'):2}
    antes = {k: valor('chamadas_http_saida_total', destino=k[0], status=k[1]) for k in esperado}
    duracao = {d: valor('chamadas_http_saida_duracao_seconds_count', destino=d) for d in ('disciplinas','solicitacoes')}
    servicos = ServicosAcademicos(httpx.Client(transport=httpx.MockTransport(endpoint)))
    servicos.turma('t')
    servicos.solicitacao('s')
    servicos.historico('a')
    assert servicos.reservar({'turma_id':'t','solicitacao_id':'s','aluno_id':'a'}) == 'SEM_VAGAS'
    servicos.liberar({'turma_id':'t','solicitacao_id':'s'})
    servicos.close()
    assert {k: valor('chamadas_http_saida_total', destino=k[0], status=k[1]) - antes[k] for k in esperado} == esperado
    assert valor('chamadas_http_saida_duracao_seconds_count', destino='disciplinas') - duracao['disciplinas'] == 3
    assert valor('chamadas_http_saida_duracao_seconds_count', destino='solicitacoes') - duracao['solicitacoes'] == 2


@pytest.mark.parametrize('falha', [httpx.ConnectError('recusada'), httpx.ReadTimeout('tempo esgotado')])
def test_falha_de_conexao_ou_timeout_conta_erro(falha):
    def endpoint(request):
        raise falha
    antes = valor('chamadas_http_saida_total', destino='solicitacoes', status='erro')
    duracao = valor('chamadas_http_saida_duracao_seconds_count', destino='solicitacoes')
    servicos = ServicosAcademicos(httpx.Client(transport=httpx.MockTransport(endpoint)))
    with pytest.raises(httpx.TransportError):
        servicos.solicitacao('s')
    servicos.close()
    assert valor('chamadas_http_saida_total', destino='solicitacoes', status='erro') - antes == 1
    assert valor('chamadas_http_saida_duracao_seconds_count', destino='solicitacoes') - duracao == 1
