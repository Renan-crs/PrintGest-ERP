"""primeiro acesso para funcionário cadastrado (M3, PRD v3.0)

- `primeiro_acesso`: flag no usuário para indicar que o primeiro login deve
  pedir definição de senha.
- `funcionario_id`: link entre Usuario e Funcionario para atribuir
  credenciais a funcionários cadastrados pelo admin.

Aditiva e reversível.

Revision ID: e8f9a0b1c2d3
Revises: d2e3f4a5b6c7
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "e8f9a0b1c2d3"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Usuario: senha_hash torna-se nullable para primeiro acesso
    # Verificar se a coluna já permite NULL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("usuario")]
    
    if "senha_hash" in columns:
        # Alterar apenas se não estiver nullable
        result = conn.execute(sa.text("SELECT is_nullable FROM information_schema.columns WHERE table_name='usuario' AND column_name='senha_hash'"))
        is_nullable = result.scalar()
        if not is_nullable:
            op.alter_column(
                "usuario",
                "senha_hash",
                existing_type=sa.String(255),
                nullable=True,
            )
    
    # Novo campo: primeiro_acesso (default False para usuarios existentes)
    if "primeiro_acesso" not in columns:
        op.add_column(
            "usuario",
            sa.Column(
                "primeiro_acesso",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    
    # Novo campo: link com funcionario
    if "funcionario_id" not in columns:
        op.add_column(
            "usuario",
            sa.Column(
                "funcionario_id",
                sa.BigInteger(),
                sa.ForeignKey("funcionario.id"),
                nullable=True,
            ),
        )
    
    if "idx_usuario_funcionario" not in [idx["name"] for idx in inspector.get_indexes("usuario")]:
        op.create_index(
            "idx_usuario_funcionario", "usuario", ["funcionario_id"]
        )


def downgrade() -> None:
    op.drop_index("idx_usuario_funcionario", table_name="usuario")
    op.drop_column("usuario", "funcionario_id")
    op.drop_column("usuario", "primeiro_acesso")
    op.alter_column(
        "usuario",
        "senha_hash",
        existing_type=sa.String(255),
        nullable=False,
    )