from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.enums import ModeloFiscal, StatusFiscal, pg_enum


class DocumentoFiscal(Base):
    __tablename__ = "documento_fiscal"
    __table_args__ = (
        Index("idx_df_status", "status", "created_at"),
        Index(
            "idx_df_venda",
            "venda_balcao_id",
            postgresql_where=text("venda_balcao_id IS NOT NULL"),
        ),
        Index(
            "idx_df_os",
            "ordem_servico_id",
            postgresql_where=text("ordem_servico_id IS NOT NULL"),
        ),
        UniqueConstraint("chave_acesso", name="uq_df_chave_acesso"),
        UniqueConstraint("modelo", "numero", "serie", name="uq_df_modelo_numero_serie"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    modelo: Mapped[ModeloFiscal] = mapped_column(pg_enum(ModeloFiscal), nullable=False)
    # Gateway de terceiro que transmitiu o documento (identificação apenas —
    # credenciais ficam na configuração da instalação, nunca no banco).
    gateway: Mapped[str | None] = mapped_column(String(40))
    gateway_id: Mapped[str | None] = mapped_column(String(120))
    ambiente: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="homologacao"
    )
    numero: Mapped[int | None] = mapped_column(Integer)
    serie: Mapped[int | None] = mapped_column(Integer)
    chave_acesso: Mapped[str | None] = mapped_column(String(44))
    status: Mapped[StatusFiscal] = mapped_column(
        pg_enum(StatusFiscal),
        nullable=False,
        server_default=StatusFiscal.RASCUNHO.value,
    )
    venda_balcao_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("venda_balcao.id")
    )
    ordem_servico_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ordem_servico.id")
    )
    cliente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cliente.id"))
    valor_nota: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    xml_path: Mapped[str | None] = mapped_column(String(500))
    danfe_path: Mapped[str | None] = mapped_column(String(500))
    protocolo: Mapped[str | None] = mapped_column(String(30))
    mensagem_retorno: Mapped[str | None] = mapped_column(Text)
    retorno_json: Mapped[dict | None] = mapped_column(JSONB)
    contingencia: Mapped[bool] = mapped_column(Boolean, server_default="false")
    tentativas: Mapped[int] = mapped_column(Integer, server_default="0")
    ultima_consulta_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text)
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FiscalEvento(Base):
    """Trilha de auditoria das operações fiscais (P0#3).

    Registra TODA tentativa de emissão/consulta/cancelamento — inclusive
    falhas — com o retorno sanitizado do gateway. Consulta sempre escopada por
    `filial_id` (isolamento entre inquilinos).
    """

    __tablename__ = "fiscal_evento"
    __table_args__ = (
        Index("idx_fiscal_evento_doc", "documento_fiscal_id", "created_at"),
        Index("idx_fiscal_evento_filial", "filial_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    documento_fiscal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documento_fiscal.id")
    )
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    mensagem: Mapped[str | None] = mapped_column(Text)
    detalhes: Mapped[dict | None] = mapped_column(JSONB)
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
