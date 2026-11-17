"""Modelos de plataforma do PRD v3.3.

- `filial`: ganha `instalacao_id` e `papel` (MATRIZ/FILIAL), vindos da licença.
- `evento_sync`: outbox — toda escrita relevante gera um evento na MESMA
  transação (RF-SY-01). A consolidação é idempotente pela chave `uuid`.
- `estacao`: registro local de estação (NÃO é licenciada individualmente).
- `licenca_evento`: log local sem segredo, retenção 24 meses (RF-DG-03).
- `backup_config` / `termo_backup`: agendamento, retenção e aceite LGPD.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EventoSync(Base):
    """Outbox de sincronização entre filiais (RF-SY-01/02)."""

    __tablename__ = "evento_sync"
    __table_args__ = (
        UniqueConstraint("uuid", name="uq_evento_sync_uuid"),
        Index("idx_evento_sync_fila", "filial_id", "seq", "enviado_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uuid: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid4())
    )
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id", ondelete="CASCADE"), nullable=False
    )
    entidade: Mapped[str] = mapped_column(String(60), nullable=False)
    entidade_id: Mapped[int | None] = mapped_column(BigInteger)
    operacao: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Estacao(Base):
    """Estação que acessa o servidor (RF-ES-01) — sem vínculo de licença."""

    __tablename__ = "estacao"
    __table_args__ = (
        UniqueConstraint("filial_id", "fingerprint", name="uq_estacao_filial_fp"),
        Index("idx_estacao_filial", "filial_id", "ultimo_acesso"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ultimo_acesso: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LicencaEvento(Base):
    """Log de ativação/renovação/mudança de estado — nunca contém segredo."""

    __tablename__ = "licenca_evento"
    __table_args__ = (Index("idx_licenca_evento_em", "em"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    estado_anterior: Mapped[str | None] = mapped_column(String(20))
    estado_novo: Mapped[str | None] = mapped_column(String(20))
    codigo_erro: Mapped[str | None] = mapped_column(String(80))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    detalhe: Mapped[dict | None] = mapped_column(JSONB)


class BackupConfig(Base):
    """Agendamento, retenção, destino e estado do backup (RF-BK/NB)."""

    __tablename__ = "backup_config"
    __table_args__ = (UniqueConstraint("filial_id", name="uq_backup_config_filial"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id", ondelete="CASCADE"), nullable=False
    )
    horario: Mapped[str] = mapped_column(String(5), nullable=False, server_default="02:00")
    retencao_dias: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="14"
    )
    destino: Mapped[str | None] = mapped_column(Text)
    neon_espelho: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ultimo_backup_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_backup_ok: Mapped[bool | None] = mapped_column(Boolean)
    ultimo_backup_tamanho: Mapped[int | None] = mapped_column(BigInteger)
    ultimo_envio_neon_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_envio_neon_ok: Mapped[bool | None] = mapped_column(Boolean)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TermoBackup(Base):
    """Aceite do termo de backup em nuvem (RF-LG-01) — auditado."""

    __tablename__ = "termo_backup"
    __table_args__ = (Index("idx_termo_backup_filial", "filial_id", "aceito_em"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id", ondelete="CASCADE"), nullable=False
    )
    versao: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="1.0"
    )
    aceito: Mapped[bool] = mapped_column(Boolean, nullable=False)
    aceito_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    usuario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    ip: Mapped[str | None] = mapped_column(String(45))
