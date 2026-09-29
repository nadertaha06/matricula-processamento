from fastapi.testclient import TestClient
from app.main import app


def test_criterios_disponiveis():
    response = TestClient(app).get('/criterios')
    assert response.status_code == 200
    assert set(response.json()) == {'coeficiente', 'periodo', 'ordem_chegada'}
