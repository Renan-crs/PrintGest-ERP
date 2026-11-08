"""sobrescrita de percentuais por fornecedor (M2, PRD v3.0 Q-04)

`preco_parametro` ganha `fornecedor_id` (FK, nullable): NULL = global da
filial; preenchido = sobrescrita para cotações daquele fornecedor. O índice
único parcial (postgresql_where) garante uma linha por escopo.

Aditiva e reversível: o down remove a coluna e o índice.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-10-27
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "preco_parametro",
        sa.Column(
            "fornecedor_id",
            sa.BigInteger(),
            sa.ForeignKey("fornecedor.id"),
            nullable=True,
        ),
    )
    op.drop_constraint("uq_preco_parametro_filial_chave", "preco_parametro")
    op.create_index(
        "uq_preco_parametro_escopo",
        "preco_parametro",
        ["filial_id", "fornecedor_id", "chave"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_preco_parametro_escopo", table_name="preco_parametro")
    op.drop_column("preco_parametro", "fornecedor_id")
    op.create_unique_constraint(
        "uq_preco_parametro_filial_chave", "preco_parametro", ["filial_id", "chave"]
    )
