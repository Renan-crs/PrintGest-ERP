"""plataforma PRD v3.3: filiais, estações, outbox, diagnóstico e backup

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-17

- `filial`: `instalacao_id` e `papel` (MATRIZ/FILIAL) definidos na ativação
  (§5.7, RF-FL-07/08).
- `evento_sync`: outbox de consolidação (RF-SY-01); `uuid` é a chave de
  idempotência e `seq` ordena a fila por filial.
- `estacao`: registro local de estação, NÃO licenciada (§4.12).
- `licenca_evento`: log local sem segredo, 24 meses (RF-DG-03).
- `backup_config` + `termo_backup`: agendamento/reenvio e aceite LGPD.

Todas as tabelas têm `filial_id` (isolamento por inquilino). Nenhum segredo é
gravado: o termo registra aceite/usuário/IP; o espelho Neon usa o cofre.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filial", sa.Column("instalacao_id", sa.String(40), nullable=True))
    op.add_column("filial", sa.Column("papel", sa.String(10), nullable=True))

    op.create_table(
        "evento_sync",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column("entidade", sa.String(60), nullable=False),
        sa.Column("entidade_id", sa.BigInteger(), nullable=True),
        sa.Column("operacao", sa.String(20), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("uuid", name="uq_evento_sync_uuid"),
    )
    op.create_index(
        "idx_evento_sync_fila", "evento_sync", ["filial_id", "seq", "enviado_em"]
    )

    op.create_table(
        "estacao",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "ultimo_acesso",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "filial_id", "fingerprint", name="uq_estacao_filial_fp"
        ),
    )
    op.create_index(
        "idx_estacao_filial", "estacao", ["filial_id", "ultimo_acesso"]
    )

    op.create_table(
        "licenca_evento",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("tipo", sa.String(40), nullable=False),
        sa.Column("estado_anterior", sa.String(20), nullable=True),
        sa.Column("estado_novo", sa.String(20), nullable=True),
        sa.Column("codigo_erro", sa.String(80), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("detalhe", JSONB(), nullable=True),
    )
    op.create_index("idx_licenca_evento_em", "licenca_evento", ["em"])

    op.create_table(
        "backup_config",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column(
            "horario", sa.String(5), nullable=False, server_default="02:00"
        ),
        sa.Column(
            "retencao_dias", sa.Integer(), nullable=False, server_default="14"
        ),
        sa.Column("destino", sa.Text(), nullable=True),
        sa.Column(
            "neon_espelho", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("ultimo_backup_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_backup_ok", sa.Boolean(), nullable=True),
        sa.Column("ultimo_backup_tamanho", sa.BigInteger(), nullable=True),
        sa.Column("ultimo_envio_neon_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_envio_neon_ok", sa.Boolean(), nullable=True),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("filial_id", name="uq_backup_config_filial"),
    )

    op.create_table(
        "termo_backup",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filial_id", sa.BigInteger(), sa.ForeignKey("filial.id"), nullable=False
        ),
        sa.Column("versao", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("aceito", sa.Boolean(), nullable=False),
        sa.Column(
            "aceito_em",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "usuario_id", sa.BigInteger(), sa.ForeignKey("usuario.id"), nullable=True
        ),
        sa.Column("ip", sa.String(45), nullable=True),
    )
    op.create_index(
        "idx_termo_backup_filial", "termo_backup", ["filial_id", "aceito_em"]
    )


def downgrade() -> None:
    op.drop_index("idx_termo_backup_filial", table_name="termo_backup")
    op.drop_table("termo_backup")
    op.drop_table("backup_config")
    op.drop_index("idx_licenca_evento_em", table_name="licenca_evento")
    op.drop_table("licenca_evento")
    op.drop_index("idx_estacao_filial", table_name="estacao")
    op.drop_table("estacao")
    op.drop_index("idx_evento_sync_fila", table_name="evento_sync")
    op.drop_table("evento_sync")
    op.drop_column("filial", "papel")
    op.drop_column("filial", "instalacao_id")
