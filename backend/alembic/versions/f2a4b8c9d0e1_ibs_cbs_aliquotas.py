"""Parametrização de alíquotas IBS/CBS (LC 214/2025)

Revision ID: f2a4b8c9d0e1
Revises: d0e1f2a4b8c9
Create Date: 2026-11-27

MIGRATION ADITIVA: cria `ibs_cbs_aliquota` (alíquotas informadas pelo
contador, com vigência) e adiciona `documento_fiscal.ibs_cbs_snapshot`
(JSONB anulável). Nenhum dado existente é alterado ou apagado e nenhuma
alíquota padrão é gravada.

Aplicação em produção: SOMENTE com autorização explícita e backup prévio.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "f2a4b8c9d0e1"
down_revision = "d0e1f2a4b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ibs_cbs_aliquota",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "empresa_id",
            sa.BigInteger(),
            sa.ForeignKey("empresa.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("cnae", sa.String(10), nullable=False),
        sa.Column("cbs_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("ibs_uf_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("ibs_municipio_pct", sa.Numeric(7, 4), nullable=True),
        sa.Column(
            "vigencia_inicio",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("vigencia_fim", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fonte",
            sa.String(10),
            nullable=False,
            server_default="contador",
        ),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column(
            "usuario_id", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "empresa_id", "cnae", "vigencia_inicio",
            name="uq_ibs_cbs_aliquota_vigencia",
        ),
        sa.CheckConstraint(
            "vigencia_fim IS NULL OR vigencia_fim > vigencia_inicio",
            name="ck_ibs_cbs_aliquota_vigencia",
        ),
        sa.CheckConstraint(
            "fonte IN ('contador', 'receita')", name="ck_ibs_cbs_aliquota_fonte"
        ),
    )
    op.add_column(
        "documento_fiscal",
        sa.Column("ibs_cbs_snapshot", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documento_fiscal", "ibs_cbs_snapshot")
    op.drop_table("ibs_cbs_aliquota")
