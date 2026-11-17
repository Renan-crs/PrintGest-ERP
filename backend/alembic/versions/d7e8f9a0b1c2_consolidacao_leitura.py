"""consolidação de leitura: cursor de mestres por filial

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8a9b0
Create Date: 2026-11-17

- `sinc_estado`: cursor (versão) já aplicado por entidade mestre em cada
  filial (RF-SY-05: descida incremental de cadastros mestres).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sinc_estado",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("filial_id", sa.BigInteger(), sa.ForeignKey("filial.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entidade", sa.String(60), nullable=False),
        sa.Column("ultima_versao", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ultimo_aplicado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "filial_id", "entidade", name="uq_sinc_estado_filial_ent"
        ),
    )
    op.create_index("idx_sinc_estado", "sinc_estado", ["filial_id", "entidade"])


def downgrade() -> None:
    op.drop_index("idx_sinc_estado", table_name="sinc_estado")
    op.drop_table("sinc_estado")
