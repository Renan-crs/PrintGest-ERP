"""item de fornecedor e cotacoes (M1, PRD v3.0 §3.2.2)

- `ordem_servico_item` ganha `tipo` ('proprio' | 'fornecedor', default
  'proprio') e `snapshot_preco` (JSONB) — o snapshot do cálculo aplicado
  (VF, percentuais, CP, VO) quando a cotação é selecionada (§3.2.1).
- Nova tabela `os_item_cotacao`: cotações de fornecedor por item, com UMA
  selecionada (índice único parcial em `selecionada`).

Aditiva e reversível: o down remove a tabela e as colunas.

Revision ID: d6e7f8a9b0c1
Revises: b5d6e7f8a9c0
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "d6e7f8a9b0c1"
down_revision = "b5d6e7f8a9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("proprio", "fornecedor", name="tipo_item_os").create(
        op.get_bind(), checkfirst=True
    )
    op.add_column(
        "ordem_servico_item",
        sa.Column(
            "tipo",
            sa.Enum("proprio", "fornecedor", name="tipo_item_os"),
            server_default="proprio",
            nullable=False,
        ),
    )
    op.add_column(
        "ordem_servico_item",
        sa.Column("snapshot_preco", JSONB(), nullable=True),
    )

    op.create_table(
        "os_item_cotacao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "item_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "fornecedor_id", sa.BigInteger(), sa.ForeignKey("fornecedor.id"), nullable=False
        ),
        sa.Column("vf", sa.Numeric(14, 2), nullable=False),
        sa.Column("validade", sa.Date(), nullable=True),
        sa.Column("prazo_dias", sa.Integer(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("anexo_path", sa.String(500), nullable=True),
        sa.Column(
            "selecionada", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("vf >= 0", name="ck_os_item_cotacao_vf"),
        sa.CheckConstraint(
            "prazo_dias IS NULL OR prazo_dias >= 0", name="ck_os_item_cotacao_prazo"
        ),
    )
    op.create_index("idx_os_item_cotacao_item", "os_item_cotacao", ["item_id"])
    op.create_index(
        "uq_os_item_cotacao_selecionada",
        "os_item_cotacao",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("selecionada"),
    )


def downgrade() -> None:
    op.drop_index("uq_os_item_cotacao_selecionada", table_name="os_item_cotacao")
    op.drop_index("idx_os_item_cotacao_item", table_name="os_item_cotacao")
    op.drop_table("os_item_cotacao")
    op.drop_column("ordem_servico_item", "snapshot_preco")
    op.drop_column("ordem_servico_item", "tipo")
    sa.Enum(name="tipo_item_os").drop(op.get_bind(), checkfirst=True)
