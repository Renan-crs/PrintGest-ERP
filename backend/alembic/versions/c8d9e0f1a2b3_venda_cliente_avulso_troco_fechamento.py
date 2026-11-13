"""venda: cliente avulso, valor recebido/troco e suporte a fechamento automatico

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-11-13

- `venda_balcao.cliente_nome_avulso`: identifica cliente nao cadastrado no PDV.
- `venda_balcao.valor_recebido` e `venda_balcao.troco`: registram pagamento em
  dinheiro para exibir no historico (troco calculado quando aplicavel).
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "venda_balcao",
        sa.Column("cliente_nome_avulso", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "venda_balcao",
        sa.Column("valor_recebido", sa.Numeric(14, 2), nullable=True),
    )
    op.add_column(
        "venda_balcao",
        sa.Column("troco", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("venda_balcao", "troco")
    op.drop_column("venda_balcao", "valor_recebido")
    op.drop_column("venda_balcao", "cliente_nome_avulso")
