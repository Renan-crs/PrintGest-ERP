"""Ficha de consumo e consumo de itens de OS — guia de variações Fase V2.

O **insumo reaproveita** `produto` (tipo `produto`, `controla_estoque=true`) e
seu saldo em `produto_estoque`: não há entidade `insumo` nem novo kardex — a
baixa real usa `movimento_estoque` com `OrigemMov.ORDEM_SERVICO`.

`custo_processo_unitario` vai na própria ficha para evitar uma terceira tabela
nesta entrega. `os_item_consumo` guarda previsto e real na mesma linha, com
`baixado_em` como guarda de idempotência da baixa.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FichaConsumo(Base):
    """Receita de produção de um produto/variante: insumos por unidade vendida."""

    __tablename__ = "ficha_consumo"
    __table_args__ = (
        Index(
            "uq_ficha_consumo_uuid",
            "uuid",
            unique=True,
            postgresql_where="uuid IS NOT NULL",
        ),
        Index(
            "idx_ficha_consumo_vigencia",
            "filial_id",
            "produto_id",
            "insumo_id",
            "vigencia_inicio",
            "vigencia_fim",
        ),
        CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio",
            name="ck_ficha_consumo_vigencia",
        ),
        CheckConstraint(
            "quantidade_por_unidade >= 0", name="ck_ficha_consumo_quantidade"
        ),
        CheckConstraint("perda_percentual >= 0", name="ck_ficha_consumo_perda"),
        CheckConstraint(
            "custo_processo_unitario >= 0", name="ck_ficha_consumo_processo"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id", ondelete="RESTRICT"), nullable=False
    )
    insumo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id", ondelete="RESTRICT"), nullable=False
    )
    quantidade_por_unidade: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False
    )
    perda_percentual: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, server_default="0"
    )
    custo_processo_unitario: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default="0"
    )
    vigencia_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    vigencia_fim: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    criado_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OsItemConsumo(Base):
    """Consumo previsto/real por insumo de um item de OS (RF-VR-20)."""

    __tablename__ = "os_item_consumo"
    __table_args__ = (
        UniqueConstraint("ordem_servico_item_id", "insumo_id", name="uq_os_item_consumo"),
        Index("idx_os_item_consumo_filial", "filial_id"),
        CheckConstraint("quantidade_prevista >= 0", name="ck_os_item_consumo_previsto"),
        CheckConstraint("quantidade_real >= 0", name="ck_os_item_consumo_real"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    ordem_servico_item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ordem_servico_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    insumo_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id", ondelete="RESTRICT"), nullable=False
    )
    quantidade_prevista: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default="0"
    )
    quantidade_real: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), nullable=False, server_default="0"
    )
    ficha_consumo_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ficha_consumo.id", ondelete="SET NULL"), nullable=True
    )
    custo_unitario_previsto: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True
    )
    baixado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    baixado_por: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    motivo_perda: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
