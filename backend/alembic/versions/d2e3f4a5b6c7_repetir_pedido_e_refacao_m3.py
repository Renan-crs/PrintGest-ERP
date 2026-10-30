"""repetir pedido e refação (M3, PRD v3.0 §3.10)

Refação: O.S. filha vinculada à original (`refacao_origem_id`), com motivo,
responsável, custo e a classificação do erro (`refacao_erro`: erro da gráfica
ou do cliente). "Repetir pedido" não precisa de colunas novas — cria uma O.S.
com os mesmos itens.

Aditiva e reversível.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ordem_servico",
        sa.Column(
            "refacao_origem_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico.id"),
            nullable=True,
        ),
    )
    op.add_column("ordem_servico", sa.Column("refacao_motivo", sa.Text(), nullable=True))
    op.add_column(
        "ordem_servico",
        sa.Column(
            "refacao_erro",
            sa.Enum("grafica", "cliente", name="refacao_erro"),
            nullable=True,
        ),
    )
    op.add_column(
        "ordem_servico",
        sa.Column(
            "refacao_responsavel_id",
            sa.BigInteger(),
            sa.ForeignKey("funcionario.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "ordem_servico",
        sa.Column("refacao_custo", sa.Numeric(14, 2), nullable=True),
    )
    op.create_check_constraint(
        "ck_os_refacao_nao_self",
        "ordem_servico",
        "refacao_origem_id IS NULL OR refacao_origem_id <> id",
    )
    op.create_index("idx_os_refacao_origem", "ordem_servico", ["refacao_origem_id"])


def downgrade() -> None:
    op.drop_index("idx_os_refacao_origem", table_name="ordem_servico")
    op.drop_constraint("ck_os_refacao_nao_self", "ordem_servico", type_="check")
    op.drop_column("ordem_servico", "refacao_custo")
    op.drop_column("ordem_servico", "refacao_responsavel_id")
    op.drop_column("ordem_servico", "refacao_erro")
    op.drop_column("ordem_servico", "refacao_motivo")
    op.drop_column("ordem_servico", "refacao_origem_id")
    sa.Enum(name="refacao_erro").drop(op.get_bind(), checkfirst=True)
