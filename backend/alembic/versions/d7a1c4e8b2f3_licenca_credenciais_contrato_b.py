"""licenca: client_id/client_secret no cofre do SO (Contrato B)

Revision ID: d7a1c4e8b2f3
Revises: c9e4f1a7b2d8
Create Date: 2026-10-20

O Contrato B (`Licenca` v4.0, ver `docs/migracao_redgest_v4.md`) troca a chave de
produto por credenciais M2M (`client_id` + `client_secret`) emitidas no handshake
e rotacionadas a cada `/validar`. A doc de integracao (§9.4/§11.4) exige que o par
fique em cofre do sistema operacional: o blob DPAPI passa de 255 caracteres e nao
cabe em `client_secret` (String(255)) — a coluna passa a `Text`, como ja foi feito
com `chave_ativacao` (b2c3d4e5f6a7).

Aditiva e reversivel. O par e guardado num unico blob (`client_id|client_secret`)
e a coluna `client_id` fica nula: metade do par nao deve sobrar em texto puro.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a1c4e8b2f3"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "licenca",
        "client_secret",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Blobs do cofre nao cabem em String(255): anula antes de encolher a coluna.
    op.execute(
        "UPDATE licenca SET client_secret = NULL "
        "WHERE client_secret IS NOT NULL AND length(client_secret) > 255"
    )
    op.alter_column(
        "licenca",
        "client_secret",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
