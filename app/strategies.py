from abc import ABC, abstractmethod


class CriterioDesempate(ABC):
    @abstractmethod
    def chave(self, candidato):
        raise NotImplementedError

    def ordenar(self, candidatos):
        return sorted(candidatos, key=self.chave)


def chegada(c):
    return (c['solicitado_em'], c['solicitacao_id'])


class PorCoeficiente(CriterioDesempate):
    def chave(self, candidato):
        return (-candidato['coeficiente'], *chegada(candidato))


class PorPeriodo(CriterioDesempate):
    def chave(self, candidato):
        return (-candidato['periodo_aluno'], *chegada(candidato))


class PorOrdemChegada(CriterioDesempate):
    def chave(self, candidato):
        return chegada(candidato)


class CriterioDesempateFactory:
    criterios = {'coeficiente':PorCoeficiente, 'periodo':PorPeriodo, 'ordem_chegada':PorOrdemChegada}

    @classmethod
    def criar(cls, nome):
        if nome not in cls.criterios:
            raise ValueError('Criterio desconhecido')
        return cls.criterios[nome]()


def faltam_pre_requisitos(exigidas, cursadas):
    return bool(set(exigidas) - set(cursadas))
