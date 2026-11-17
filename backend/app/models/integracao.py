"""Integrações com aplicações de terceiros (PRD v3.3 §3.6).

Somente METADADOS ficam no banco: nome, base URL, cabeçalho de autenticação,
opções e máscaras. API key/token e certificado ficam no cofre do SO
(`cofre_integracoes`), nunca em texto no banco, log ou backup.
"""

from datetime import datetime

from sqlalchemy import (
    Enum,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import TipoIntegracao


class Integracao(Base):
    __tablename__ = "integracao"
    __table_args__ = (
        UniqueConstraint("filial_id", "tipo", name="uq_integracao_filial_tipo"),
        Index("idx_integracao_filial", "filial_id", "ativo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    # Tipo enum no banco; create_type=False porque a migration cria o tipo.
    tipo: Mapped[TipoIntegracao] = mapped_column(
        Enum(TipoIntegracao, name="tipo_integracao", create_type=False),
        nullable=False,
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    provedor: Mapped[str | None] = mapped_column(String(120))
    base_url: Mapped[str | None] = mapped_column(String(500))
    auth_header: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="Authorization"
    )
    auth_prefix: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default="Bearer "
    )
    ambiente: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="homologacao"
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # Caminhos/parâmetros do provedor (NÃO contém segredos).
    opcoes: Mapped[dict | None] = mapped_column(JSONB)
    # Apenas máscaras e indicadores — o valor real está no cofre.
    credencial_mascara: Mapped[str | None] = mapped_column(String(40))
    certificado_mascara: Mapped[str | None] = mapped_column(String(40))
    tem_credencial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    tem_certificado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ultimo_teste_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_teste_ok: Mapped[bool | None] = mapped_column(Boolean)
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IntegracaoEvento(Base):
    """Trilha de auditoria — nunca contém segredos."""

    __tablename__ = "integracao_evento"
    __table_args__ = (
        Index("idx_integracao_evento", "integracao_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    integracao_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("integracao.id")
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    mensagem: Mapped[str | None] = mapped_column(Text)
    detalhes: Mapped[dict | None] = mapped_column(JSONB)
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
