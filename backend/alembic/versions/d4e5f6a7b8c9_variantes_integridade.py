"""Integridade das variantes de produto

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-11-22

- UNIQUE por (filial, pai, tamanho, marca, cor) — evita duplicidade semântica
  quando o `codigo` do pai muda e uma nova combinação é gerada.
- FK composta (produto_pai_id, filial_id) -> produto(id, filial_id) com
  ON DELETE RESTRICT — impede que uma filha aponte para outro inquilino.

Pré-checagem em produção: 0 duplicatas, 0 pais cross-tenant, 0 variantes.
Backup: branch Neon `backup-pre-migration-variantes-20261122` (LSN 0/3605DD0).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None

_COLS = [
    "filial_id",
    "produto_pai_id",
    sa.text("COALESCE(atrib_tamanho, '')"),
    sa.text("COALESCE(atrib_marca, '')"),
    sa.text("COALESCE(atrib_cor, '')"),
]


def upgrade() -> None:
    op.create_index(
        "uq_produto_variante_atributos",
        "produto",
        _COLS,
        unique=True,
        postgresql_where=sa.text("produto_pai_id IS NOT NULL"),
    )
    op.create_unique_constraint(
        "uq_produto_id_filial", "produto", ["id", "filial_id"]
    )
    op.drop_constraint(
        "produto_produto_pai_id_fkey", "produto", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_produto_pai_mesma_filial",
        "produto",
        "produto",
        ["produto_pai_id", "filial_id"],
        ["id", "filial_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_produto_pai_mesma_filial", "produto", type_="foreignkey"
    )
    op.create_foreign_key(
        "produto_produto_pai_id_fkey",
        "produto",
        "produto",
        ["produto_pai_id"],
        ["id"],
    )
    op.drop_constraint("uq_produto_id_filial", "produto", type_="unique")
    op.drop_index("uq_produto_variante_atributos", table_name="produto")
