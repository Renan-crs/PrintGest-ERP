"""Estado local da consolidação (PRD v3.3 §5.8).

`sinc_estado` guarda o cursor (versão) já aplicado por entidade mestre em cada
filial —RF-SY-05: descida incremental por `versao`/`atualizado_em`.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SyncEstado(Base):
    __tablename__ = "sinc_estado"
    __table_args__ = (
        UniqueConstraint("filial_id", "entidade", name="uq_sinc_estado_filial_ent"),
        Index("idx_sinc_estado", "filial_id", "entidade"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id", ondelete="CASCADE"), nullable=False
    )
    entidade: Mapped[str] = mapped_column(String(60), nullable=False)
    ultima_versao: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    ultimo_aplicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
