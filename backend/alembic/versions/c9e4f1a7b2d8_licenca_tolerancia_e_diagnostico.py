"""licenca: tolerancia offline e diagnostico da ultima tentativa

Revision ID: c9e4f1a7b2d8
Revises: f2a3b4c5d6e7
Create Date: 2026-10-18

Plano `docs/plano_resiliencia_licenca.md`, etapa E2. Acrescenta à tabela
`licenca`:
  - `tolerancia_expira_em`  — até quando o sistema opera normal com o token vencido;
  - `ultima_tentativa_em`   — quando foi a última tentativa de renovação;
  - `ultimo_erro`           — causa da última falha (diagnóstico/mensagem).

Aditiva e reversível: colunas anuláveis, sem mudança de dados existentes.
"""

import sqlalchemy as sa

from alembic import op

# Revision identifiers, used by Alembic.
revision = "c9e4f1a7b2d8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "licenca",
        sa.Column("tolerancia_expira_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "licenca",
        sa.Column("ultima_tentativa_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("licenca", sa.Column("ultimo_erro", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("licenca", "ultimo_erro")
    op.drop_column("licenca", "ultima_tentativa_em")
    op.drop_column("licenca", "tolerancia_expira_em")
