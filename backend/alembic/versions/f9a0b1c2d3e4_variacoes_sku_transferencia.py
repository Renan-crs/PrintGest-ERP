"""variações de produto (SKU/atributos) e transferência entre filiais

Revision ID: f9a0b1c2d3e4
Revises: d7e8f9a0b1c2
Create Date: 2026-11-18

- `produto`: `sku` (único por filial), `uuid` global, `produto_pai_id`,
  atributos de domínio fechado (tamanho, marca, cor).
- `transferencia_estoque`: documento de saída/recebimento entre filiais (§5.6).
- enums `estado_transferencia` e novos valores de `origem_mov`.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f9a0b1c2d3e4"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Enum de estado da transferência.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'estado_transferencia') THEN "
        "CREATE TYPE estado_transferencia AS ENUM ('enviada','recebida','cancelada'); "
        "END IF; END $$;"
    )
    # OrigemMov ganha duas novas variantes (ADD VALUE é idempotente).
    with op.get_context().autocommit_block():
        for valor in ("transferencia_saida", "transferencia_entrada"):
            op.execute(
                f"ALTER TYPE origem_mov ADD VALUE IF NOT EXISTS '{valor}'"
            )

    op.add_column("produto", sa.Column("sku", sa.String(64), nullable=True))
    op.add_column("produto", sa.Column("uuid", sa.String(36), nullable=True))
    op.add_column(
        "produto",
        sa.Column("produto_pai_id", sa.BigInteger(), sa.ForeignKey("produto.id"), nullable=True),
    )
    op.add_column("produto", sa.Column("atrib_tamanho", sa.String(40), nullable=True))
    op.add_column("produto", sa.Column("atrib_marca", sa.String(60), nullable=True))
    op.add_column("produto", sa.Column("atrib_cor", sa.String(60), nullable=True))
    op.create_unique_constraint(
        "uq_produto_filial_sku", "produto", ["filial_id", "sku"]
    )
    op.create_index("idx_produto_pai", "produto", ["produto_pai_id"])

    op.create_table(
        "transferencia_estoque",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("numero", sa.String(30), nullable=False),
        sa.Column(
            "filial_origem_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "filial_destino_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "produto_id", sa.BigInteger(), sa.ForeignKey("produto.id"), nullable=False
        ),
        sa.Column("quantidade", sa.Numeric(12, 3), nullable=False),
        sa.Column(
            "estado",
            sa.String(20),
            nullable=False,
            server_default="enviada",
        ),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column(
            "enviado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "enviado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "recebido_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column("recebido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_transferencia_origem", "transferencia_estoque", ["filial_origem_id", "estado"]
    )
    op.create_index(
        "idx_transferencia_destino", "transferencia_estoque", ["filial_destino_id", "estado"]
    )


def downgrade() -> None:
    op.drop_index("idx_transferencia_destino", table_name="transferencia_estoque")
    op.drop_index("idx_transferencia_origem", table_name="transferencia_estoque")
    op.drop_table("transferencia_estoque")
    op.drop_index("idx_produto_pai", table_name="produto")
    op.drop_constraint("uq_produto_filial_sku", "produto", type_="unique")
    for coluna in ("atrib_cor", "atrib_marca", "atrib_tamanho", "produto_pai_id", "uuid", "sku"):
        op.drop_column("produto", coluna)
    op.execute("DROP TYPE IF EXISTS estado_transferencia")
