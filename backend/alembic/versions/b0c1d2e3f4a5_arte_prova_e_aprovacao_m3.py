"""arte, prova e aprovação (M3, PRD v3.0 §3.5)

Tabelas:
- `arte_versao` — versões do arquivo de arte por OS (v1, v2…)
- `arte_aprovacao` — decisão do cliente sobre uma versão (aprovada / ajuste)
- `link_publico` — token para acesso externo (relay D-03 no futuro)

Aditiva e reversível.

Revision ID: b0c1d2e3f4a5
Revises: a9b0c1d2e3f4
Create Date: 2026-10-27
"""

import sqlalchemy as sa

from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- arte_versao: versões do arquivo
    op.create_table(
        "arte_versao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column(
            "os_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=False),
        sa.Column("caminho", sa.String(500), nullable=False),
        sa.Column("hash_sha256", sa.String(64), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=False),
        sa.Column("criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id")),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("os_id", "versao", name="uq_arte_versao_os_versao"),
        sa.CheckConstraint("versao > 0", name="ck_arte_versao_positiva"),
        sa.CheckConstraint("tamanho_bytes > 0", name="ck_arte_versao_tamanho"),
    )
    op.create_index("idx_arte_versao_os", "arte_versao", ["os_id"])

    # --- arte_aprovacao: decisão do cliente
    op.create_table(
        "arte_aprovacao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column(
            "versao_id",
            sa.BigInteger(),
            sa.ForeignKey("arte_versao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "decisao",
            sa.Enum("aprovada", "ajuste", name="decisao_arte"),
            nullable=False,
        ),
        sa.Column("comentarios", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_arte_aprovacao_versao", "arte_aprovacao", ["versao_id"])

    # --- link_publico: token para acesso externo (relay D-03)
    op.create_table(
        "link_publico",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column(
            "os_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "tipo",
            sa.Enum("prova", "orcamento", name="tipo_link_publico"),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "usado", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_link_publico_os", "link_publico", ["os_id"])


def downgrade() -> None:
    op.drop_index("idx_link_publico_os", table_name="link_publico")
    op.drop_table("link_publico")
    sa.Enum(name="tipo_link_publico").drop(op.get_bind(), checkfirst=True)

    op.drop_index("idx_arte_aprovacao_versao", table_name="arte_aprovacao")
    op.drop_table("arte_aprovacao")
    sa.Enum(name="decisao_arte").drop(op.get_bind(), checkfirst=True)

    op.drop_index("idx_arte_versao_os", table_name="arte_versao")
    op.drop_table("arte_versao")
