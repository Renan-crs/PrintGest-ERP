"""cliente: condição de pagamento antecipado (pagamento_adiantado / sinal)

Revision ID: d4b5c6e7f8a0
Revises: c3e7a5b90123
Create Date: 2026-10-09

Adiciona ao cliente a condição de pagamento exigida na abertura de O.S./venda:
  - `pagamento_adiantado`: exige 100% do valor na criação;
  - `sinal`: exige um percentual (`sinal_pct`, padrão 50%);
As duas colunas são mutuamente exclusivas (CHECK).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4b5c6e7f8a0"
down_revision: Union[str, None] = "c3e7a5b90123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cliente",
        sa.Column(
            "pagamento_adiantado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "cliente",
        sa.Column(
            "sinal", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "cliente",
        sa.Column(
            "sinal_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("50"),
        ),
    )
    op.create_check_constraint(
        "ck_cliente_adiantamento_exclusivo",
        "cliente",
        "NOT (pagamento_adiantado AND sinal)",
    )
    op.create_check_constraint(
        "ck_cliente_sinal_pct", "cliente", "sinal_pct BETWEEN 0 AND 100"
    )


def downgrade() -> None:
    op.drop_constraint("ck_cliente_sinal_pct", "cliente", type_="check")
    op.drop_constraint("ck_cliente_adiantamento_exclusivo", "cliente", type_="check")
    op.drop_column("cliente", "sinal_pct")
    op.drop_column("cliente", "sinal")
    op.drop_column("cliente", "pagamento_adiantado")
