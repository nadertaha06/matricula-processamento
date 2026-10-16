from typing import Literal, Annotated
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db import session_scope
from app.models import Lote, Avaliacao
from app.service import lista_espera
from app.strategies import CriterioDesempateFactory

from app.auth import Principal, get_principal, require_permission, require_internal, check_owner

router = APIRouter(dependencies=[Depends(get_principal)])


class CriterioInput(BaseModel):
    criterio: Literal['coeficiente','periodo','ordem_chegada']


@router.get('/criterios')
def criterios():
    return list(CriterioDesempateFactory.criterios)


@router.put('/turmas/{turma_id}/criterio', dependencies=[Depends(require_permission('manage:processamento'))])
def configurar(data: CriterioInput, turma_id: str = Path(min_length=1, max_length=36), session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    session.execute(text('SELECT pg_advisory_xact_lock(220926)'))
    lote = session.get(Lote, turma_id)
    if lote is None:
        session.add(Lote(turma_id=turma_id, criterio=data.criterio))
    else:
        lote.criterio = data.criterio
    session.commit()
    return {'turma_id':turma_id,'criterio':data.criterio}


@router.get('/turmas/{turma_id}/lista-espera')
def espera(turma_id: str, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    # Same lock as the worker: concurrent first reads cannot insert duplicate policies.
    session.execute(text('SELECT pg_advisory_xact_lock(220926)'))
    resultado = lista_espera(session, turma_id)
    session.commit()
    if principal.has('manage:processamento'):
        return resultado
    return [{'posicao': c['posicao'], 'solicitacao_id': c['solicitacao_id']}
            for c in resultado if not principal.internal and c['aluno_id'] == principal.sub]


@router.get('/avaliacoes/{solicitacao_id}')
def avaliacao(solicitacao_id: str, session: Session = Depends(session_scope), principal: Principal = Depends(get_principal)):
    a = session.get(Avaliacao, solicitacao_id)
    if a is None:
        raise HTTPException(404, 'Avaliacao nao encontrada')
    check_owner(principal, a.candidato['aluno_id'], 'manage:processamento')
    return {'solicitacao_id':a.solicitacao_id,'turma_id':a.turma_id,'resultado':a.resultado,'motivo':a.motivo,'revisao':a.revisao}
