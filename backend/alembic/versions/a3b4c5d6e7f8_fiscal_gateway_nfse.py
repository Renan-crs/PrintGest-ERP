"""fiscal: gateway de terceiro, NFS-e e auditoria de eventos (P0#3)

Revision ID: a3b4c5d6e7f8
Revises: e2f3a4b5c6d7
Create Date: 2026-11-17

- `modelo_fiscal`: novo valor `nfse` (emitida por API de terceiro).
- `documento_fiscal`: gateway/gateway_id/ambiente, última consulta e auditoria
  de cancelamento (motivo/quando).
- `fiscal_evento`: trilha de emissão/consulta/cancelamento (inclusive falhas).

Nenhuma credencial do gateway é gravada — apenas identificação do provedor.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

_VALORES_BASE = "nfe", "nfce"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE modelo_fiscal ADD VALUE IF NOT EXISTS 'nfse'"
        )

    op.add_column("documento_fiscal", sa.Column("gateway", sa.String(40), nullable=True))
    op.add_column(
        "documento_fiscal", sa.Column("gateway_id", sa.String(120), nullable=True)
    )
    op.add_column(
        "documento_fiscal",
        sa.Column(
            "ambiente",
            sa.String(20),
            nullable=False,
            server_default="homologacao",
        ),
    )
    op.add_column(
        "documento_fiscal",
        sa.Column("ultima_consulta_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documento_fiscal",
        sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documento_fiscal",
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
    )

    op.create_table(
        "fiscal_evento",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "documento_fiscal_id",
            sa.BigInteger(),
            sa.ForeignKey("documento_fiscal.id"),
            nullable=True,
        ),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column("detalhes", JSONB(), nullable=True),
        sa.Column(
            "criado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_fiscal_evento_doc",
        "fiscal_evento",
        ["documento_fiscal_id", "created_at"],
    )
    op.create_index(
        "idx_fiscal_evento_filial", "fiscal_evento", ["filial_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_fiscal_evento_filial", table_name="fiscal_evento")
    op.drop_index("idx_fiscal_evento_doc", table_name="fiscal_evento")
    op.drop_table("fiscal_evento")
    op.drop_column("documento_fiscal", "motivo_cancelamento")
    op.drop_column("documento_fiscal", "cancelado_em")
    op.drop_column("documento_fiscal", "ultima_consulta_em")
    op.drop_column("documento_fiscal", "ambiente")
    op.drop_column("documento_fiscal", "gateway_id")
    op.drop_column("documento_fiscal", "gateway")

    # PostgreSQL não remove valores de enum: reconstrói o tipo sem `nfse`.
    with op.get_context().autocommit_block():
        op.execute("ALTER TABLE documento_fiscal ALTER COLUMN modelo TYPE text")
        op.execute("DROP TYPE modelo_fiscal")
        valores = ", ".join(f"'{v}'" for v in _VALORES_BASE)
        op.execute(f"CREATE TYPE modelo_fiscal AS ENUM ({valores})")
        op.execute(
            "ALTER TABLE documento_fiscal ALTER COLUMN modelo TYPE modelo_fiscal "
            "USING modelo::text::modelo_fiscal"
        )
