"""modulo_projetos: etiqueta, checklist, comentario e atividade (Fase 2)

Revision ID: f2a3b4c5d6e7
Revises: e7c1d4a2b9f6
Create Date: 2026-10-17

Fase 2 (Cartão rico) do módulo Projetos (PRD Módulo Projetos §9/RF10–RF14):
etiquetas coloridas, checklists com itens, comentários (resposta em 1 nível) e
log de atividade append-only.

Aditivo e reversível: nenhuma tabela/coluna existente muda e **nenhum tipo
PostgreSQL novo** é criado (todas as colunas novas são escalares). `cartao_anexo`
e `capa_anexo_id` ficam para a Fase 3.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# Revision identifiers, used by Alembic.
revision = "f2a3b4c5d6e7"
down_revision = "e7c1d4a2b9f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "etiqueta",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column("nome", sa.String(length=60), nullable=True),
        sa.Column("cor", sa.String(length=9), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_etiqueta_filial", "etiqueta", ["filial_id", "nome"])

    op.create_table(
        "cartao_etiqueta",
        sa.Column(
            "cartao_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "etiqueta_id",
            sa.BigInteger(),
            sa.ForeignKey("etiqueta.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "cartao_checklist",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "cartao_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("posicao", sa.Numeric(24, 12), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_cartao_checklist_cartao", "cartao_checklist", ["cartao_id", "posicao"]
    )

    op.create_table(
        "cartao_checklist_item",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "checklist_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao_checklist.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("texto", sa.String(length=500), nullable=False),
        sa.Column("concluido", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "responsavel_id", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column("data_entrega", sa.Date(), nullable=True),
        sa.Column("posicao", sa.Numeric(24, 12), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_cartao_checklist_item_checklist",
        "cartao_checklist_item",
        ["checklist_id", "posicao"],
    )

    op.create_table(
        "cartao_comentario",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "cartao_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=False,
        ),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column(
            "resposta_a_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao_comentario.id"),
            nullable=True,
        ),
        sa.Column("excluido", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("editado_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_cartao_comentario_cartao",
        "cartao_comentario",
        ["cartao_id", "criado_em"],
    )

    op.create_table(
        "cartao_atividade",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "cartao_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "usuario_id", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("dados", JSONB, nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_cartao_atividade_cartao", "cartao_atividade", ["cartao_id", "criado_em"]
    )


def downgrade() -> None:
    op.drop_index("idx_cartao_atividade_cartao", table_name="cartao_atividade")
    op.drop_table("cartao_atividade")
    op.drop_index("idx_cartao_comentario_cartao", table_name="cartao_comentario")
    op.drop_table("cartao_comentario")
    op.drop_index(
        "idx_cartao_checklist_item_checklist", table_name="cartao_checklist_item"
    )
    op.drop_table("cartao_checklist_item")
    op.drop_index("idx_cartao_checklist_cartao", table_name="cartao_checklist")
    op.drop_table("cartao_checklist")
    op.drop_table("cartao_etiqueta")
    op.drop_index("idx_etiqueta_filial", table_name="etiqueta")
    op.drop_table("etiqueta")
