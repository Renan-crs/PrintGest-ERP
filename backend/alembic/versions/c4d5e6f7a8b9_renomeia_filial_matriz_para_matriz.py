"""renomeia a unidade 'Filial Matriz' para 'Matriz'

Revisão de UX da top bar: a primeira unidade semeada chamava-se "Filial
Matriz" — contraditório (a unidade é a matriz; filial é outra coisa). O
bootstrap novo semeia "Matriz"; esta migração corrige os bancos já criados.

Reversível: o down devolve "Matriz" para "Filial Matriz". A suposição é a
mesma do up invertido — nenhum operador criou, à mão, outra unidade chamada
exatamente "Matriz" antes desta migração (produto em piloto, sem clientes
finais).

Revision ID: c4d5e6f7a8b9
Revises: d7a1c4e8b2f3
Create Date: 2026-10-25
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "d7a1c4e8b2f3"
branch_labels = None
depends_on = None

_ANTIGO = "Filial Matriz"
_NOVO = "Matriz"


def upgrade() -> None:
    op.execute(
        f"UPDATE filial SET nome = '{_NOVO}' WHERE nome = '{_ANTIGO}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE filial SET nome = '{_ANTIGO}' WHERE nome = '{_NOVO}'"
    )
