"""licenca: chave de produto (RedGest /licencas-software)

Revision ID: a1b2c3d4e5f6
Revises: c9e4f1a7b2d8
Create Date: 2026-10-18

Troca o modelo local de licenciamento do fluxo `online_periodic`
(CNPJ + codigo_licenca -> JWT) para o Contrato C do manual do RedGest:
**chave de produto** validada online em `/api/v1/licencas-software/validar/`.

Acrescenta a `licenca`:
  - `chave_ativacao`        — chave digitada pelo usuário (XXXX-XXXX-XXXX-XXXX);
  - `maquina_fingerprint`   — fingerprint determinístico da estação;
  - `expira_em`             — vigência retornada pelo RedGest (nula = vitalícia);
  - `limite_ativacoes` / `ativacoes_realizadas` — cota e uso.

Libera para nulo as colunas que pertenciam ao fluxo antigo
(`licenca_redgest_id`, `cnpj`, `codigo_licenca`), agora sem uso.

Aditiva e reversível para o schema. O `downgrade` volta as colunas antigas a
`NOT NULL` — pressupõe que não existam linhas do Contrato C (o estado anterior à
migração).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c9e4f1a7b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "licenca", sa.Column("chave_ativacao", sa.String(length=19), nullable=True)
    )
    op.add_column(
        "licenca", sa.Column("maquina_fingerprint", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "licenca", sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("licenca", sa.Column("limite_ativacoes", sa.Integer(), nullable=True))
    op.add_column(
        "licenca", sa.Column("ativacoes_realizadas", sa.Integer(), nullable=True)
    )
    op.alter_column(
        "licenca",
        "licenca_redgest_id",
        existing_type=sa.String(length=40),
        nullable=True,
    )
    op.alter_column("licenca", "cnpj", existing_type=sa.CHAR(length=14), nullable=True)
    op.alter_column(
        "licenca", "codigo_licenca", existing_type=sa.String(length=40), nullable=True
    )
    op.alter_column(
        "licenca",
        "sistema",
        existing_type=sa.String(length=60),
        server_default="printgest",
    )


def downgrade() -> None:
    op.alter_column(
        "licenca",
        "sistema",
        existing_type=sa.String(length=60),
        server_default="grafica_erp",
    )
    op.alter_column(
        "licenca", "codigo_licenca", existing_type=sa.String(length=40), nullable=False
    )
    op.alter_column("licenca", "cnpj", existing_type=sa.CHAR(length=14), nullable=False)
    op.alter_column(
        "licenca",
        "licenca_redgest_id",
        existing_type=sa.String(length=40),
        nullable=False,
    )
    op.drop_column("licenca", "ativacoes_realizadas")
    op.drop_column("licenca", "limite_ativacoes")
    op.drop_column("licenca", "expira_em")
    op.drop_column("licenca", "maquina_fingerprint")
    op.drop_column("licenca", "chave_ativacao")
