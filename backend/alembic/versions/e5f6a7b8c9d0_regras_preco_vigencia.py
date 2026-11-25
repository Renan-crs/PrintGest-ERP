"""Tabelas de preço, regras com vigência e snapshot no documento (Fase V1)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-24

MIGRATION ADITIVA: cria duas tabelas novas e adiciona duas colunas JSONB
anuláveis. Nenhuma coluna existente é alterada, renomeada ou removida e
nenhum dado é apagado — os registros atuais continuam com `preco_snapshot`
nulo e o comportamento legado de preço permanece intacto até uma regra ser
cadastrada.

Regras de negócio atendidas: RF-VR-08 (precedência cliente/filial/padrão),
RF-VR-12 (regra nunca editada; alteração cria nova com vigência) e RF-VR-21
(snapshot da regra usada no documento).

Aplicação em produção: SOMENTE com autorização explícita e backup prévio.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tabela_preco",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "cliente_id",
            sa.BigInteger(),
            sa.ForeignKey("cliente.id"),
            nullable=True,
        ),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("padrao", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "NOT (padrao IS TRUE AND cliente_id IS NOT NULL)",
            name="ck_tabela_preco_padrao_sem_cliente",
        ),
    )
    op.create_index(
        "uq_tabela_preco_uuid",
        "tabela_preco",
        ["uuid"],
        unique=True,
        postgresql_where=sa.text("uuid IS NOT NULL"),
    )
    op.create_index(
        "idx_tabela_preco_escopo",
        "tabela_preco",
        ["cliente_id", "filial_id", "padrao"],
    )

    op.create_table(
        "regra_preco",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column(
            "tabela_preco_id",
            sa.BigInteger(),
            sa.ForeignKey("tabela_preco.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "produto_id",
            sa.BigInteger(),
            sa.ForeignKey("produto.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "preco_base",
            sa.Numeric(14, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column("faixas", JSONB(), nullable=True),
        sa.Column("modificadores", JSONB(), nullable=True),
        sa.Column("minimo", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "modo_faixa",
            sa.String(20),
            nullable=False,
            server_default="TODA_A_QUANTIDADE",
        ),
        sa.Column(
            "vigencia_inicio",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("vigencia_fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "prioridade",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "criado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio",
            name="ck_regra_preco_vigencia",
        ),
        sa.CheckConstraint("preco_base >= 0", name="ck_regra_preco_base"),
        sa.CheckConstraint("prioridade >= 0", name="ck_regra_preco_prioridade"),
    )
    op.create_index(
        "uq_regra_preco_uuid",
        "regra_preco",
        ["uuid"],
        unique=True,
        postgresql_where=sa.text("uuid IS NOT NULL"),
    )
    op.create_index(
        "idx_regra_preco_vigencia",
        "regra_preco",
        ["tabela_preco_id", "produto_id", "vigencia_inicio", "vigencia_fim"],
    )

    # Snapshot do cálculo: colunas novas, anuláveis. Dados antigos não mudam.
    op.add_column(
        "venda_balcao_item", sa.Column("preco_snapshot", JSONB(), nullable=True)
    )
    op.add_column(
        "ordem_servico_item", sa.Column("preco_snapshot", JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("ordem_servico_item", "preco_snapshot")
    op.drop_column("venda_balcao_item", "preco_snapshot")
    op.drop_index("idx_regra_preco_vigencia", table_name="regra_preco")
    op.drop_index("uq_regra_preco_uuid", table_name="regra_preco")
    op.drop_table("regra_preco")
    op.drop_index("idx_tabela_preco_escopo", table_name="tabela_preco")
    op.drop_index("uq_tabela_preco_uuid", table_name="tabela_preco")
    op.drop_table("tabela_preco")
