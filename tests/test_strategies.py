import pytest
from app.strategies import CriterioDesempateFactory, faltam_pre_requisitos

pytestmark = pytest.mark.unit


def candidatos():
    return [
        {'solicitacao_id':'c','coeficiente':9,'periodo_aluno':2,'solicitado_em':'2026-09-01T10:02:00+00:00'},
        {'solicitacao_id':'b','coeficiente':8,'periodo_aluno':5,'solicitado_em':'2026-09-01T10:01:00+00:00'},
        {'solicitacao_id':'a','coeficiente':9,'periodo_aluno':3,'solicitado_em':'2026-09-01T10:00:00+00:00'}]


@pytest.mark.parametrize('nome,esperada', [('coeficiente',['a','c','b']),('periodo',['b','a','c']),('ordem_chegada',['a','b','c'])])
def test_ordenacao(nome, esperada):
    assert [x['solicitacao_id'] for x in CriterioDesempateFactory.criar(nome).ordenar(candidatos())] == esperada


def test_desempate_total_por_identificador():
    c = candidatos()[0]
    values = [{**c,'solicitacao_id':'b'},{**c,'solicitacao_id':'a'}]
    for nome in CriterioDesempateFactory.criterios:
        assert CriterioDesempateFactory.criar(nome).ordenar(values)[0]['solicitacao_id'] == 'a'


def test_criterio_invalido():
    with pytest.raises(ValueError):
        CriterioDesempateFactory.criar('aleatorio')


@pytest.mark.parametrize('exigidas,cursadas,falta', [([],[],False),(['A'],[],True),(['A'],['A','B'],False),(['A','B'],['A'],True)])
def test_pre_requisitos(exigidas, cursadas, falta):
    assert faltam_pre_requisitos(exigidas,cursadas) is falta
