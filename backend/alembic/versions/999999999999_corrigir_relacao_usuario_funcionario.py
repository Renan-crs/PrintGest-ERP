"""corrigir_relacao_usuario_funcionario: explicitar foreign_keys nas relações

Corrige o erro AmbiguousForeignKeysError ao especificar explicitamente
as foreign_keys nas relações entre Usuario e Funcionario.

Revision ID: 999999999999
Revises: f1a09c3b2d84
Create Date: 2026-11-02

"""

# revision identifiers, used by Alembic.
revision = "999999999999"
down_revision = "f1a09c3b2d84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Esta migration não altera o schema - apenas documenta a correção
    # do modelo SQLAlchemy para especificar foreign_keys corretamente.
    # As FK já existem no banco:
    # - funcionario.usuario_id -> usuario.id
    # - usuario.funcionario_id -> funcionario.id
    #
    # A correção está no código Python, não no schema.
    pass


def downgrade() -> None:
    pass
