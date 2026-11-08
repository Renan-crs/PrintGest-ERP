"""modulo_projetos: quadro, quadro_lista, cartao e cartao_membro

Revision ID: e7c1d4a2b9f6
Revises: d4b5c6e7f8a0
Create Date: 2026-10-17

Fase 1 (Núcleo) do módulo Projetos (PRD Módulo Projetos §9): o quadro deixa de
ser uma visão sobre `/v1/os` e passa a ter entidade própria, com listas
configuráveis (§4) e cartões de 0..1 O.S. (RN1).

Aditivo e reversível: nenhuma tabela ou coluna existente é alterada — `/v1/os`,
`ordem_servico` e o quadro atual seguem intactos. `ordem_servico.posicao_kanban`
não existia neste schema (campo descartado pelo PRD), portanto não há o que
remover. `cartao.capa_anexo_id` e as demais tabelas de "cartão rico"
(etiqueta, checklist, anexo, comentário, atividade) entram nas fases 2 e 3.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7c1d4a2b9f6"
down_revision: str | None = "d4b5c6e7f8a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tipos novos deste módulo.
tipo_lista = sa.Enum(
    "orcamento",
    "usuario",
    "aprovacao",
    "producao",
    "terceiro",
    "final",
    "livre",
    name="tipo_lista",
)
origem_membro = sa.Enum("manual", "lista", "atribuidor", name="origem_membro")

# `status_os` já existe desde o baseline (ordem_servico). Usa `PgEnum` (e não o
# `sa.Enum` genérico) porque só a variante do dialeto honra `create_type=False`,
# evitando o `CREATE TYPE` duplicado dentro do `op.create_table`.
status_os = PgEnum(
    "aberto",
    "aprovado",
    "producao",
    "pronta",
    "entregue",
    "cancelado",
    "convertido",
    name="status_os",
    create_type=False,
)


def upgrade() -> None:
    # Os tipos `tipo_lista` e `origem_membro` são criados automaticamente pelo
    # `op.create_table` (dialeto PostgreSQL emite o `CREATE TYPE` da coluna);
    # por isso não há criação explícita aqui. `status_os` já existe desde o
    # baseline e é referenciado com `create_type=False`.
    op.create_table(
        "quadro",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "nome", sa.String(length=120), nullable=False, server_default="Projetos"
        ),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("filial_id", name="uq_quadro_filial"),
    )

    op.create_table(
        "quadro_lista",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "quadro_id",
            sa.BigInteger(),
            sa.ForeignKey("quadro.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("posicao", sa.Numeric(24, 12), nullable=False),
        sa.Column("tipo", tipo_lista, nullable=False, server_default="livre"),
        sa.Column("status_os", status_os, nullable=True),
        sa.Column(
            "usuario_dono_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column(
            "fornecedor_id",
            sa.BigInteger(),
            sa.ForeignKey("fornecedor.id"),
            nullable=True,
        ),
        sa.Column("arquivada", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_quadro_lista_quadro", "quadro_lista", ["quadro_id", "posicao"])

    op.create_table(
        "cartao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "lista_id",
            sa.BigInteger(),
            sa.ForeignKey("quadro_lista.id"),
            nullable=False,
        ),
        sa.Column("posicao", sa.Numeric(24, 12), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("data_entrega", sa.Date(), nullable=True),
        sa.Column("lembrete_min", sa.Integer(), nullable=True),
        sa.Column("concluido", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ordem_servico_id",
            sa.BigInteger(),
            sa.ForeignKey("ordem_servico.id"),
            nullable=True,
        ),
        sa.Column(
            "ultimo_responsavel_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column(
            "terceiro_fornecedor_id",
            sa.BigInteger(),
            sa.ForeignKey("fornecedor.id"),
            nullable=True,
        ),
        sa.Column("terceiro_prazo", sa.Date(), nullable=True),
        sa.Column("terceiro_custo", sa.Numeric(14, 2), nullable=True),
        sa.Column("arquivado", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("ordem_servico_id", name="uq_cartao_ordem_servico"),
    )
    op.create_index("idx_cartao_lista", "cartao", ["lista_id", "posicao"])
    op.create_index("idx_cartao_filial_arquivado", "cartao", ["filial_id", "arquivado"])

    op.create_table(
        "cartao_membro",
        sa.Column(
            "cartao_id",
            sa.BigInteger(),
            sa.ForeignKey("cartao.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "usuario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            primary_key=True,
        ),
        sa.Column("origem", origem_membro, nullable=False, server_default="manual"),
        sa.Column(
            "adicionado_por",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id"),
            nullable=True,
        ),
        sa.Column(
            "adicionado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("cartao_id", "usuario_id", name="uq_cartao_membro"),
    )
    op.create_index("idx_cartao_membro_usuario", "cartao_membro", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("idx_cartao_membro_usuario", table_name="cartao_membro")
    op.drop_table("cartao_membro")
    op.drop_index("idx_cartao_filial_arquivado", table_name="cartao")
    op.drop_index("idx_cartao_lista", table_name="cartao")
    op.drop_table("cartao")
    op.drop_index("idx_quadro_lista_quadro", table_name="quadro_lista")
    op.drop_table("quadro_lista")
    op.drop_table("quadro")

    bind = op.get_bind()
    origem_membro.drop(bind, checkfirst=True)
    tipo_lista.drop(bind, checkfirst=True)
