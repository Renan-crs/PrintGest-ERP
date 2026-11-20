"""Integridade de produtos e variações no banco

Revision ID: c2d3e4f5a6b7
Revises: a0b1c2d3e4f5
Create Date: 2026-11-20

- `uuid` e `codigo_barras` passam a ter UNIQUE parcial (NULL permitido).
- `CHECK` impede `tipo='servico' AND controla_estoque=true`.

Antes de aplicar em produção foi verificado que não há duplicatas nem
serviços com estoque (0/0/0), e criado o branch de backup
`backup-pre-migration-produtos-20261120` (LSN 0/3517E18).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_produto_uuid",
        "produto",
        ["uuid"],
        unique=True,
        postgresql_where=sa.text("uuid IS NOT NULL"),
    )
    op.create_index(
        "uq_produto_codigo_barras",
        "produto",
        ["codigo_barras"],
        unique=True,
        postgresql_where=sa.text("codigo_barras IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_produto_servico_sem_estoque",
        "produto",
        "tipo::text <> 'servico' OR controla_estoque = false",
    )


def downgrade() -> None:
    op.drop_constraint("ck_produto_servico_sem_estoque", "produto", type_="check")
    op.drop_index("uq_produto_codigo_barras", table_name="produto")
    op.drop_index("uq_produto_uuid", table_name="produto")
