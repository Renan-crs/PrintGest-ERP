"""os: sinal (valor e forma) persistidos e saldo derivado

Revision ID: d1e2f3a4b5c6
Revises: c8d9e0f1a2b3
Create Date: 2026-11-15

- `ordem_servico.valor_sinal`: valor do sinal/adiantamento recebido/registrado.
- `ordem_servico.forma_sinal`: forma de pagamento do sinal.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordem_servico",
        sa.Column("valor_sinal", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "ordem_servico",
        sa.Column("forma_sinal", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ordem_servico", "forma_sinal")
    op.drop_column("ordem_servico", "valor_sinal")
