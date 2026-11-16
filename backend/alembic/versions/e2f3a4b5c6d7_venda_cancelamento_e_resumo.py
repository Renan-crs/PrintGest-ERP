"""venda: motivo/auditoria de cancelamento (parcial P0#3)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-11-16

- `venda_balcao.motivo_cancelamento`: motivo informado ao cancelar.
- `venda_balcao.cancelado_em`: data/hora do cancelamento.
- `venda_balcao.cancelado_por`: usuário que cancelou.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "venda_balcao",
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
    )
    op.add_column(
        "venda_balcao",
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "venda_balcao",
        sa.Column(
            "cancelado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("venda_balcao", "cancelado_por")
    op.drop_column("venda_balcao", "cancelado_em")
    op.drop_column("venda_balcao", "motivo_cancelamento")
