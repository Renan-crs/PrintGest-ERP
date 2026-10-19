"""licenca: chave de ativacao no cofre do SO

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-19

A doc de integracao do RedGest (§9.4) exige a chave de ativacao em cofre do
sistema operacional. A partir de agora o servico grava `chave_ativacao` cifrada
com DPAPI (escopo de maquina): o blob tem ~385 caracteres e nao cabe nos 19 da
coluna original — a coluna passa a `Text`.

Linhas antigas (texto puro) seguem legiveis: o servico reconhece valores sem o
prefixo `dpapi:v1:` e os usa como estao.

Aditiva e reversivel. O `downgrade` anula os valores que nao cabem em 19
caracteres (blobs do cofre) antes de encolher a coluna.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "licenca",
        "chave_ativacao",
        existing_type=sa.String(length=19),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Blobs do cofre nao cabem em String(19): anula para o encolhimento passar.
    op.execute(
        "UPDATE licenca SET chave_ativacao = NULL "
        "WHERE chave_ativacao IS NOT NULL AND length(chave_ativacao) > 19"
    )
    op.alter_column(
        "licenca",
        "chave_ativacao",
        existing_type=sa.Text(),
        type_=sa.String(length=19),
        existing_nullable=True,
    )
