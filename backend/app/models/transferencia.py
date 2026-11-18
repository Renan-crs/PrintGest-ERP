"""Transferência de estoque entre filiais (PRD §5.6).

Fluxo de DOIS passos, sem transação distribuída:
  - `enviada`: saída na origem (estoque decrementado, kardex SAIDA).
  - `recebida`: confirmação no destino (estoque incrementado, kardex ENTRADA).

O destino só recebe o saldo após a confirmação. Cada filial é dona do seu
lado — não há escrita cruzada no mesmo banco.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import EstadoTransferencia, pg_enum


class TransferenciaEstoque(Base):
    __tablename__ = "transferencia_estoque"
    __table_args__ = (
        Index("idx_transferencia_origem", "filial_origem_id", "estado"),
        Index("idx_transferencia_destino", "filial_destino_id", "estado"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    numero: Mapped[str] = mapped_column(String(30), nullable=False)
    filial_origem_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    filial_destino_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id"), nullable=False
    )
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    estado: Mapped[EstadoTransferencia] = mapped_column(
        pg_enum(EstadoTransferencia),
        nullable=False,
        server_default=EstadoTransferencia.ENVIADA.value,
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    enviado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    enviado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    recebido_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    recebido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
