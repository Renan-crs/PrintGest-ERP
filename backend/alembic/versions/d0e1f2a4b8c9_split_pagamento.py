"""Split payment — múltiplas formas de pagamento por venda

Revision ID: d0e1f2a4b8c9
Revises: a7b8c9d0e1f2
Create Date: 2026-11-27

MIGRATION ADITIVA: cria `venda_pagamento` (uma linha por forma). A coluna
`venda_balcao.forma_pagamento` é mantida como forma principal para
compatibilidade com relatórios, fiscal e sync legados. Nenhum dado existente é
alterado ou apagado; vendas antigas seguem com uma única forma implícita.

Aplicação em produção: SOMENTE com autorização explícita e backup prévio.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d0e1f2a4b8c9"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "venda_pagamento",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "venda_balcao_id",
            sa.BigInteger(),
            sa.ForeignKey("venda_balcao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "forma_pagamento",
            sa.Enum(
                "dinheiro", "cartao_credito", "cartao_debito", "pix",
                "boleto", "fiado", name="forma_pagamento",
            ),
            nullable=False,
        ),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "parcelas", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("valor_recebido", sa.Numeric(14, 2), nullable=True),
        sa.Column("troco", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "venda_balcao_id", "seq", name="uq_venda_pagamento_seq"
        ),
        sa.CheckConstraint("valor >= 0", name="ck_venda_pagamento_valor"),
        sa.CheckConstraint("parcelas >= 1", name="ck_venda_pagamento_parcelas"),
    )
    op.create_index(
        "idx_venda_pagamento_venda", "venda_pagamento", ["venda_balcao_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_venda_pagamento_venda", table_name="venda_pagamento")
    op.drop_table("venda_pagamento")
