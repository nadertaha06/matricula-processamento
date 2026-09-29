from fastapi.testclient import TestClient
from app.main import app


def test_configuracao_do_desempate():
    client = TestClient(app)
    r = client.put('/turmas/turma-1/criterio', json={'criterio':'periodo'})
    assert r.status_code == 200
    assert r.json()['criterio'] == 'periodo'


def test_lista_espera_vazia():
    assert TestClient(app).get('/turmas/turma-1/lista-espera').json() == []
