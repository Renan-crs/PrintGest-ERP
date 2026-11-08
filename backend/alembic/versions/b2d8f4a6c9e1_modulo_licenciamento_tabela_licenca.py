"""modulo licenciamento: tabela local licenca (RedGest online_periodic)

Revision ID: b2d8f4a6c9e1
Revises: f1a09c3b2d84
Create Date: 2026-09-21

Cria `licenca`, que guarda o vínculo da instalação com o RedGest (CNPJ + código +
credenciais retornadas na ativação) e o último JWT validado, permitindo renovação
por polling e o modo de leitura local (PRD v2.0 §3.4 / §3.2.6).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d8f4a6c9e1"
down_revision: str | None = "f1a09c3b2d84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "licenca",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("licenca_redgest_id", sa.String(length=40), nullable=False),
        sa.Column(
            "sistema",
            sa.String(length=60),
            server_default="grafica_erp",
            nullable=False,
        ),
        sa.Column("cnpj", sa.CHAR(length=14), nullable=False),
        sa.Column("codigo_licenca", sa.String(length=40), nullable=False),
        sa.Column("plano", sa.String(length=20), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="aguardando", nullable=False
        ),
        sa.Column("client_id", sa.String(length=120), nullable=True),
        sa.Column("client_secret", sa.String(length=255), nullable=True),
        sa.Column("entitlements", postgresql.JSONB(), nullable=True),
        sa.Column("token_jwt", sa.Text(), nullable=True),
        sa.Column("token_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_validacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "atualizada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("licenca_redgest_id"),
    )
    op.create_index("idx_licenca_status", "licenca", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_licenca_status", table_name="licenca")
    op.drop_table("licenca")
