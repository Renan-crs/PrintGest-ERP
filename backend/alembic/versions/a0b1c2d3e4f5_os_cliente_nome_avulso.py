"""O.S./orçamento: cliente não cadastrado (nome avulso)

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-11-19

Permite lançar O.S./orçamento com cliente não cadastrado, sem exigir a criação
prévia do cadastro (Fase 2 do autocomplete de cliente). Segue o mesmo padrão
de `venda_balcao.cliente_nome_avulso`.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordem_servico",
        sa.Column("cliente_nome_avulso", sa.String(160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ordem_servico", "cliente_nome_avulso")
