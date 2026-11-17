"""integrações com apps de terceiros (PRD v3.3 §3.6)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-17

- `tipo_integracao`: fiscal, email, pagamento, generica.
- `integracao`: metadados + máscaras (CREDENCIAIS NÃO ficam no banco).
- `integracao_evento`: auditoria sem segredos.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE TYPE idempotente (SQLAlchemy create(checkfirst=True) usa um
    # inspector com cache e pode tentar criar um tipo já existente após
    # DROP SCHEMA + reexecução da migration — visto nos testes).
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tipo_integracao') THEN "
        "CREATE TYPE tipo_integracao AS ENUM "
        "('fiscal', 'email', 'pagamento', 'generica'); "
        "END IF; END $$;"
    )
    # String: o tipo PG enum foi criado no SQL acima; usar String evita que
    # o SQLAlchemy tente recriá-lo no create_table (evento _on_table_create).
    tipo = sa.String(30)

    op.create_table(
        "integracao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column("tipo", tipo, nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("provedor", sa.String(120), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column(
            "auth_header",
            sa.String(80),
            nullable=False,
            server_default="Authorization",
        ),
        sa.Column(
            "auth_prefix", sa.String(40), nullable=False, server_default="Bearer "
        ),
        sa.Column(
            "ambiente",
            sa.String(20),
            nullable=False,
            server_default="homologacao",
        ),
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("opcoes", JSONB(), nullable=True),
        sa.Column("credencial_mascara", sa.String(40), nullable=True),
        sa.Column("certificado_mascara", sa.String(40), nullable=True),
        sa.Column(
            "tem_credencial",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "tem_certificado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "ultimo_teste_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("ultimo_teste_ok", sa.Boolean(), nullable=True),
        sa.Column(
            "criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "filial_id", "tipo", name="uq_integracao_filial_tipo"
        ),
    )
    op.create_index("idx_integracao_filial", "integracao", ["filial_id", "ativo"])

    op.create_table(
        "integracao_evento",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id",
            sa.BigInteger(),
            sa.ForeignKey("filial.id"),
            nullable=False,
        ),
        sa.Column(
            "integracao_id",
            sa.BigInteger(),
            sa.ForeignKey("integracao.id"),
            nullable=True,
        ),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=True),
        sa.Column("detalhes", JSONB(), nullable=True),
        sa.Column(
            "criado_por", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_integracao_evento", "integracao_evento", ["integracao_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_integracao_evento", table_name="integracao_evento")
    op.drop_table("integracao_evento")
    op.drop_index("idx_integracao_filial", table_name="integracao")
    op.drop_table("integracao")
    op.execute("DROP TYPE IF EXISTS tipo_integracao")
