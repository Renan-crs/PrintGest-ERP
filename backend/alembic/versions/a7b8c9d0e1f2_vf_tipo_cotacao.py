"""VF unitário ou total na cotação de fornecedor

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-27

MIGRATION ADITIVA: adiciona uma coluna com default `'unitario'` (compatível
com todas as cotações existentes) e um CHECK. Nenhum dado é alterado ou
apagado. O valor `'total'` indica que o VF informado é o montante cobrado pelo
fornecedor pela quantidade inteira do item (ex.: R$ 35,00 por 24 adesivos).

Aplicação em produção: SOMENTE com autorização explícita e backup prévio.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "os_item_cotacao",
        sa.Column(
            "vf_tipo",
            sa.String(10),
            nullable=False,
            server_default="unitario",
        ),
    )
    op.create_check_constraint(
        "ck_os_item_cotacao_vf_tipo",
        "os_item_cotacao",
        "vf_tipo IN ('unitario', 'total')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_os_item_cotacao_vf_tipo", "os_item_cotacao", type_="check"
    )
    op.drop_column("os_item_cotacao", "vf_tipo")
