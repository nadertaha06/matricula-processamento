import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.mark.unit
@pytest.mark.parametrize("method,path", [('get', '/criterios'), ('get', '/turmas/x/lista-espera'), ('get', '/avaliacoes/x'), ('put', '/turmas/x/criterio')])
def test_routes_require_authentication(method, path):
    assert getattr(TestClient(app), method)(path).status_code == 401


def test_waitlist_only_discloses_own_position():
    from sqlalchemy.orm import Session
    from app.db import get_engine
    from app.models import Avaliacao
    from app.auth import get_principal, Principal
    with Session(get_engine()) as session:
        for student, score in [('auth0|a', 8), ('auth0|b', 9)]:
            session.add(Avaliacao(solicitacao_id=student, turma_id='t', resultado='EM_ESPERA',
                candidato={'aluno_id':student,'solicitacao_id':student,'turma_id':'t',
                    'coeficiente':score,'periodo_aluno':2,'solicitado_em':'2026-10-14T12:00:00Z'}))
        session.commit()
    app.dependency_overrides[get_principal] = lambda: Principal('auth0|a', frozenset())
    try:
        c = TestClient(app)
        assert c.get('/turmas/t/lista-espera').json() == [{'posicao':2,'solicitacao_id':'auth0|a'}]
        assert c.get('/avaliacoes/auth0|b').status_code == 403
        assert c.get('/avaliacoes/auth0|a').status_code == 200
        assert c.put('/turmas/t/criterio', json={'criterio':'coeficiente'}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_principal, None)
