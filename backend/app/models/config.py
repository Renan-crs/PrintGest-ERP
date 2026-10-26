from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


from decimal import Decimal

class PrecoReajusteHistorico(Base):
    __tablename__ = "preco_reajuste_historico"
    __table_args__ = (
        CheckConstraint(
            "tipo_reajuste IN ('percentual', 'valor_fixo')",
            name="ck_reajuste_tipo",
        ),
        Index("idx_reajuste_data", "executado_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=False
    )
    tipo_reajuste: Mapped[str] = mapped_column(String(12), nullable=False)
    valor_reajuste: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    criterio: Mapped[str] = mapped_column(Text, nullable=False)
    itens_afetados: Mapped[int] = mapped_column(Integer, nullable=False)
    detalhes: Mapped[list] = mapped_column(JSONB, nullable=False)
    executado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )