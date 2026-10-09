"""funcionario: coluna observacoes

Revision ID: c3e7a5b90123
Revises: b2d8f4a6c9e1
Create Date: 2026-09-23

Adiciona `observacoes` (Text) ao cadastro de funcionários, alinhando a tela do
frontend (que já envia o campo) com o contrato da API.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3e7a5b90123"
down_revision: Union[str, None] = "b2d8f4a6c9e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "funcionario",
        sa.Column("observacoes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("funcionario", "observacoes")