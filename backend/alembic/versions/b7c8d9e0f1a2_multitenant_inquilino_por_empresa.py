"""multitenant: inquilino (empresa) por instalacao no banco compartilhado

Revision ID: b7c8d9e0f1a2
Revises: a4f2c8e1b9d7
Create Date: 2026-11-11

O projeto Neon do PrintGest e UNICO e compartilhado entre graficas: cada
instalacao (daemon) passa a declarar o inquilino que serve via
`PRINTGEST_EMPRESA_CNPJ`, e o isolamento logico passa a ser:

1) `licenca.empresa_id` — cada inquilino tem a propria linha de licenca no
   banco compartilhado. Backfill: casa pelo `cnpj` ja gravado na linha;
   fallback = primeira empresa (o bootstrap demo).
2) Unicidades globais viram unicidades POR FILIAL — dois inquilinos podem ter
   o mesmo CPF/CNPJ de cliente, codigo de produto ou login 'admin' sem
   conflito: usuario.login, cliente.cpf_cnpj, fornecedor.cpf_cnpj,
   funcionario.cpf e produto.codigo.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a4f2c8e1b9d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tabela, constraint global antiga, nova constraint por filial, coluna)
_UNICIDADES_POR_FILIAL = [
    ("usuario", "usuario_login_key", "uq_usuario_filial_login", "login"),
    ("cliente", "cliente_cpf_cnpj_key", "uq_cliente_filial_cpf_cnpj", "cpf_cnpj"),
    (
        "fornecedor",
        "fornecedor_cpf_cnpj_key",
        "uq_fornecedor_filial_cpf_cnpj",
        "cpf_cnpj",
    ),
    ("funcionario", "funcionario_cpf_key", "uq_funcionario_filial_cpf", "cpf"),
    ("produto", "produto_codigo_key", "uq_produto_filial_codigo", "codigo"),
]


def upgrade() -> None:
    # --- 1) licenca.empresa_id: o inquilino dono da licenca ------------------
    op.add_column(
        "licenca",
        sa.Column("empresa_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_licenca_empresa", "licenca", "empresa", ["empresa_id"], ["id"]
    )
    op.create_index("idx_licenca_empresa", "licenca", ["empresa_id"])
    # Backfill: casa pelo cnpj legado da linha; sem casamento, adota a
    # primeira empresa (bootstrap demo) para nao deixar licenca orfa.
    op.execute(
        "UPDATE licenca l SET empresa_id = e.id FROM empresa e "
        "WHERE e.cnpj = l.cnpj AND l.empresa_id IS NULL"
    )
    op.execute(
        "UPDATE licenca SET empresa_id = (SELECT id FROM empresa ORDER BY id LIMIT 1) "
        "WHERE empresa_id IS NULL"
    )

    # --- 2) unicidade por filial (escopo de inquilino) -----------------------
    for tabela, antiga, nova, coluna in _UNICIDADES_POR_FILIAL:
        op.drop_constraint(antiga, tabela, type_="unique")
        op.create_unique_constraint(nova, tabela, ["filial_id", coluna])


def downgrade() -> None:
    # ATENCAO: recriar a unicidade GLOBAL falha se duas filiais tiverem o
    # mesmo valor (ex.: dois 'admin') — dedup manual antes do downgrade.
    for tabela, antiga, nova, coluna in _UNICIDADES_POR_FILIAL:
        op.drop_constraint(nova, tabela, type_="unique")
        op.create_unique_constraint(antiga, tabela, [coluna])
    op.drop_index("idx_licenca_empresa", table_name="licenca")
    op.drop_constraint("fk_licenca_empresa", "licenca", type_="foreignkey")
    op.drop_column("licenca", "empresa_id")
