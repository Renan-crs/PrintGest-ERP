"""merge heads for usuario-funcionario relationship fix

Revision ID: 8559861e3efc
Revises: 999999999999, e8f9a0b1c2d3
Create Date: 2026-11-02 20:16:23.437007

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8559861e3efc"
down_revision: str | None = ("999999999999", "e8f9a0b1c2d3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
