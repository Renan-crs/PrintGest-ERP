"""funcionario.usuario_id: link reverso com o usuário de login (M3 §3.10)

O modelo `Funcionario` declara `usuario_id` (FK para `usuario.id`) e a relação
`Funcionario.usuario`, mas nenhuma migration criava a coluna. Como o SQLAlchemy
seleciona **todas** as colunas mapeadas, qualquer consulta a `funcionario`
(OS, vendas, dashboard...) falhava com `UndefinedColumn`.

A migration é idempotente: em bases que já receberam a coluna por ajuste manual
(ou que rodaram a correção do modelo), ela não faz nada.

Revision ID: a4f2c8e1b9d7
Revises: 8559861e3efc
Create Date: 2026-11-03
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4f2c8e1b9d7"
down_revision = "8559861e3efc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    colunas = {col["name"] for col in inspector.get_columns("funcionario")}
    if "usuario_id" not in colunas:
        op.add_column(
            "funcionario",
            sa.Column(
                "usuario_id",
                sa.BigInteger(),
                sa.ForeignKey("usuario.id", name="fk_funcionario_usuario"),
                nullable=True,
            ),
        )
    indices = {idx["name"] for idx in inspector.get_indexes("funcionario")}
    if "idx_funcionario_usuario" not in indices:
        op.create_index("idx_funcionario_usuario", "funcionario", ["usuario_id"])

    # `usuario.senha_hash` precisa aceitar NULL para o primeiro acesso do
    # funcionário (senha definida no primeiro login). A migration
    # `e8f9a0b1c2d3` tentou isso, mas inverteu a checagem de `is_nullable`.
    colunas_usuario = {
        col["name"]: col for col in inspector.get_columns("usuario")
    }
    senha = colunas_usuario.get("senha_hash")
    if senha is not None and not senha["nullable"]:
        op.alter_column(
            "usuario",
            "senha_hash",
            existing_type=sa.String(255),
            nullable=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indices = {idx["name"] for idx in inspector.get_indexes("funcionario")}
    if "idx_funcionario_usuario" in indices:
        op.drop_index("idx_funcionario_usuario", table_name="funcionario")
    colunas = {col["name"] for col in inspector.get_columns("funcionario")}
    if "usuario_id" in colunas:
        op.drop_column("funcionario", "usuario_id")
