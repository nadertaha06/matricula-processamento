import httpx
import pytest
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
