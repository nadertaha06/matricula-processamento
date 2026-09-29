from sqlalchemy import String, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Lote(Base):
    __tablename__ = 'lote'
    turma_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    criterio: Mapped[str] = mapped_column(String(30))


class Avaliacao(Base):
    __tablename__ = 'avaliacao'
    solicitacao_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turma_id: Mapped[str] = mapped_column(String(36), index=True)
    candidato: Mapped[dict] = mapped_column(JSON)
    resultado: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    revisao: Mapped[int] = mapped_column(Integer, default=0)
