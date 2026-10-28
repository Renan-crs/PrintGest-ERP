"""status da OS incorpora a arte (M3, PRD v3.0 §3.5)

Adiciona `aguardando_arte` e `aguardando_aprovacao` ao enum `status_os`
("Status da OS incorpora 'Aguardando arte' e 'Aguardando aprovação'"). O tipo
é compartilhado por `ordem_servico.status` e `cartao.status_os`.

Reversível: o downgrade reconstrói o tipo sem os valores novos (PostgreSQL
não remove valores de enum) e reativa as duas colunas com USING cast.

Revision ID: c1d2e3f4a5b6
Revises: b0c1d2e3f4a5
Create Date: 2026-10-28
"""

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None

# Valores do tipo SEM os acréscimos deste migration (usados no downgrade).
_VALORES_BASE = [
    "aberto", "aprovado", "producao", "pronta", "entregue", "cancelado",
    "convertido",
]
_NOVOS = ["aguardando_arte", "aguardando_aprovacao"]


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE não pode rodar em transação em PostgreSQL < 12.
    with op.get_context().autocommit_block():
        for valor in _NOVOS:
            op.execute(f"ALTER TYPE status_os ADD VALUE '{valor}'")


def downgrade() -> None:
    # PostgreSQL não remove valores de enum: reconstrói o tipo sem os novos
    # valores e reaponta as duas colunas que o usam (ordem_servico.status e
    # cartao.status_os). Linhas nos status novos não podem existir aqui —
    # quem removeu o uso antes de regredir as guarda o valor como texto.
    with op.get_context().autocommit_block():
        op.execute("ALTER TABLE ordem_servico ALTER COLUMN status TYPE text")
        op.execute("ALTER TABLE cartao ALTER COLUMN status_os TYPE text")
        op.execute("DROP TYPE status_os")
        valores = ", ".join(f"'{v}'" for v in _VALORES_BASE)
        op.execute(f"CREATE TYPE status_os AS ENUM ({valores})")
        op.execute(
            "ALTER TABLE ordem_servico ALTER COLUMN status TYPE status_os "
            "USING status::text::status_os"
        )
        op.execute(
            "ALTER TABLE cartao ALTER COLUMN status_os TYPE status_os "
            "USING status_os::text::status_os"
        )
