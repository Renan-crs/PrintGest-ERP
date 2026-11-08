"""parametro de precificacao (preco_parametro) do M1

Tabela do PRD v3.0 §5 para os parâmetros globais de precificação por filial
(`acrescimo_fornecedor_pct` = 130, `markup_orcamento_pct` = 6). Aditiva e
reversível: o down remove a tabela.

Revision ID: b5d6e7f8a9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401 — compat com o padrão local

from alembic import op

# revision identifiers, used by Alembic.
revision = "b5d6e7f8a9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preco_parametro",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column("chave", sa.String(40), nullable=False),
        sa.Column("valor", sa.Numeric(7, 3), nullable=False),
        sa.Column(
            "usuario_id", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "filial_id", "chave", name="uq_preco_parametro_filial_chave"
        ),
        sa.CheckConstraint("valor >= 0", name="ck_preco_parametro_valor"),
    )


def downgrade() -> None:
    op.drop_table("preco_parametro")
