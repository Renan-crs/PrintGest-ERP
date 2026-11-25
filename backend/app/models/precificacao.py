"""Tabelas de preço e regras com vigência — guia de variações Fase V1.

Modelo adotado (simplificação documentada): uma `RegraPreco` por
`(tabela, produto, vigência)` guarda faixas e modificadores em JSONB, em vez
de uma linha por tipo de regra do modelo teórico do guia. Isso mantém o
número de tabelas enxuto e permite que o mesmo motor `calcular_linha` seja
usado para analisar todas as regras. A precedência cliente → filial → padrão e
a vigência são resolvidas em `services/regra_preco_service.py`.
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
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TabelaPreco(Base):
    """Tabela padrão, por cliente ou por filial (RF-VR-08)."""

    __tablename__ = "tabela_preco"
    __table_args__ = (
        Index("uq_tabela_preco_uuid", "uuid", unique=True, postgresql_where="uuid IS NOT NULL"),
        Index("idx_tabela_preco_escopo", "cliente_id", "filial_id", "padrao"),
        CheckConstraint(
            "NOT (padrao IS TRUE AND cliente_id IS NOT NULL)",
            name="ck_tabela_preco_padrao_sem_cliente",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Sempre pertence a uma filial do inquilino — nunca é global.
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    cliente_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("cliente.id"), nullable=True
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    padrao: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RegraPreco(Base):
    """Regra vigente de preço de um produto/variante numa tabela (RF-VR-12).

    Nunca é editada depois de usada: alterar o preço cria uma nova linha com
    `vigencia_inicio` nova e encerra a anterior em `vigencia_fim`.
    """

    __tablename__ = "regra_preco"
    __table_args__ = (
        Index("uq_regra_preco_uuid", "uuid", unique=True, postgresql_where="uuid IS NOT NULL"),
        Index(
            "idx_regra_preco_vigencia",
            "tabela_preco_id",
            "produto_id",
            "vigencia_inicio",
            "vigencia_fim",
        ),
        CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio",
            name="ck_regra_preco_vigencia",
        ),
        CheckConstraint("preco_base >= 0", name="ck_regra_preco_base"),
        CheckConstraint("prioridade >= 0", name="ck_regra_preco_prioridade"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tabela_preco_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tabela_preco.id", ondelete="RESTRICT"), nullable=False
    )
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id", ondelete="RESTRICT"), nullable=False
    )
    preco_base: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, server_default="0"
    )
    faixas: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    modificadores: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    minimo: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    modo_faixa: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="TODA_A_QUANTIDADE"
    )
    vigencia_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    vigencia_fim: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    prioridade: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
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
