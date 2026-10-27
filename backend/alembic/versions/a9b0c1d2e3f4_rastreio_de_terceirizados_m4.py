"""rastreio de terceirizados (M4, PRD v3.0 §3.6)

Tabela `os_terceirizado`: ciclo de vida do item terceirizado dentro da OS —
envio ao fornecedor, previsão de retorno, recebimento e conferência de
qualidade (ok / refação). Atraso de retorno (previsão vencida sem retorno)
alimenta o dashboard.

Aditiva e reversível.

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "os_terceirizado",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False),
        sa.Column(
            "os_id", sa.BigInteger(), sa.ForeignKey("ordem_servico.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id", sa.BigInteger(), sa.ForeignKey("ordem_servico_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cotacao_id", sa.BigInteger(), sa.ForeignKey("os_item_cotacao.id"), nullable=True),
        sa.Column("pedido_compra_id", sa.BigInteger(), sa.ForeignKey("pedido_compra.id"), nullable=True),
        sa.Column("data_envio", sa.Date(), nullable=False),
        sa.Column("previsao_retorno", sa.Date(), nullable=True),
        sa.Column("data_retorno", sa.Date(), nullable=True),
        sa.Column(
            "conferencia",
            sa.Enum("pendente", "ok", "refacao", name="conferencia_terceirizado"),
            nullable=False,
            server_default="pendente",
        ),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "data_retorno IS NULL OR data_retorno >= data_envio",
            name="ck_os_terceirizado_retorno_apos_envio",
        ),
        sa.CheckConstraint(
            "previsao_retorno IS NULL OR previsao_retorno >= data_envio",
            name="ck_os_terceirizado_previsao_apos_envio",
        ),
    )
    op.create_index("idx_os_terceirizado_os", "os_terceirizado", ["os_id"])
    op.create_index("idx_os_terceirizado_item", "os_terceirizado", ["item_id"])


def downgrade() -> None:
    op.drop_index("idx_os_terceirizado_item", table_name="os_terceirizado")
    op.drop_index("idx_os_terceirizado_os", table_name="os_terceirizado")
    op.drop_table("os_terceirizado")
    sa.Enum(name="conferencia_terceirizado").drop(op.get_bind(), checkfirst=True)
