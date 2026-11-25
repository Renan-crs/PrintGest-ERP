"""Fichas de consumo e consumo de itens de OS (Fase V2)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-24

MIGRATION ADITIVA: cria apenas duas tabelas novas. Nenhuma coluna existente é
alterada, nenhuma constraint de produto/OS é modificada e nenhum dado é apagado.
O insumo reaproveita `produto` + `produto_estoque`; a baixa real reaproveita
`movimento_estoque` com `OrigemMov.ORDEM_SERVICO`.

Aplicação em produção: SOMENTE com autorização explícita e backup prévio.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ficha_consumo",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "produto_id",
            sa.BigInteger(),
            sa.ForeignKey("produto.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "insumo_id",
            sa.BigInteger(),
            sa.ForeignKey("produto.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "quantidade_por_unidade", sa.Numeric(14, 4), nullable=False
        ),
        sa.Column(
            "perda_percentual",
            sa.Numeric(6, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "custo_processo_unitario",
            sa.Numeric(14, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "vigencia_inicio",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("vigencia_fim", sa.DateTime(timezone=True), nullable=True),
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
            name="ck_ficha_consumo_vigencia",
        ),
        sa.CheckConstraint(
            "quantidade_por_unidade >= 0", name="ck_ficha_consumo_quantidade"
        ),
        sa.CheckConstraint("perda_percentual >= 0", name="ck_ficha_consumo_perda"),
        sa.CheckConstraint(
            "custo_processo_unitario >= 0", name="ck_ficha_consumo_processo"
        ),
    )
    op.create_index(
        "uq_ficha_consumo_uuid",
        "ficha_consumo",
        ["uuid"],
        unique=True,
        postgresql_where=sa.text("uuid IS NOT NULL"),
    )
    op.create_index(
        "idx_ficha_consumo_vigencia",
        "ficha_consumo",
        ["filial_id", "produto_id", "insumo_id", "vigencia_inicio", "vigencia_fim"],
    )

    op.create_table(
        "os_item_consumo",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "ordem_servico_item_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "insumo_id",
            sa.BigInteger(),
            sa.ForeignKey("produto.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "quantidade_prevista",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "quantidade_real",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "ficha_consumo_id",
            sa.BigInteger(),
            sa.ForeignKey("ficha_consumo.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("custo_unitario_previsto", sa.Numeric(14, 4), nullable=True),
        sa.Column("baixado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "baixado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column("motivo_perda", sa.String(255), nullable=True),
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
        sa.UniqueConstraint(
            "ordem_servico_item_id", "insumo_id", name="uq_os_item_consumo"
        ),
        sa.CheckConstraint(
            "quantidade_prevista >= 0", name="ck_os_item_consumo_previsto"
        ),
        sa.CheckConstraint("quantidade_real >= 0", name="ck_os_item_consumo_real"),
    )
    op.create_index("idx_os_item_consumo_filial", "os_item_consumo", ["filial_id"])


def downgrade() -> None:
    op.drop_index("idx_os_item_consumo_filial", table_name="os_item_consumo")
    op.drop_table("os_item_consumo")
    op.drop_index("idx_ficha_consumo_vigencia", table_name="ficha_consumo")
    op.drop_index("uq_ficha_consumo_uuid", table_name="ficha_consumo")
    op.drop_table("ficha_consumo")
