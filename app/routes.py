from typing import Literal, Annotated
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.db import session_scope
from app.models import Lote, Avaliacao
from app.service import lista_espera
from app.strategies import CriterioDesempateFactory

router = APIRouter()


class CriterioInput(BaseModel):
    criterio: Literal['coeficiente','periodo','ordem_chegada']


@router.get('/criterios')
def criterios():
    return list(CriterioDesempateFactory.criterios)


@router.put('/turmas/{turma_id}/criterio')
def configurar(data: CriterioInput, turma_id: str = Path(min_length=1, max_length=36), session: Session = Depends(session_scope)):
    session.execute(text('SELECT pg_advisory_xact_lock(220926)'))
    lote = session.get(Lote, turma_id)
    if lote is None:
        session.add(Lote(turma_id=turma_id, criterio=data.criterio))
    else:
        lote.criterio = data.criterio
    session.commit()
    return {'turma_id':turma_id,'criterio':data.criterio}


@router.get('/turmas/{turma_id}/lista-espera')
def espera(turma_id: str, session: Session = Depends(session_scope)):
    # Same lock as the worker: concurrent first reads cannot insert duplicate policies.
    session.execute(text('SELECT pg_advisory_xact_lock(220926)'))
    resultado = lista_espera(session, turma_id)
    session.commit()
    return resultado


@router.get('/avaliacoes/{solicitacao_id}')
def avaliacao(solicitacao_id: str, session: Session = Depends(session_scope)):
    a = session.get(Avaliacao, solicitacao_id)
    if a is None:
        raise HTTPException(404, 'Avaliacao nao encontrada')
    return {'solicitacao_id':a.solicitacao_id,'turma_id':a.turma_id,'resultado':a.resultado,'motivo':a.motivo,'revisao':a.revisao}
