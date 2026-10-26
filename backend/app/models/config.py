from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


from decimal import Decimal

class PrecoReajusteHistorico(Base):
    __tablename__ = "preco_reajuste_historico"
    __table_args__ = (
        CheckConstraint(
            "tipo_reajuste IN ('percentual', 'valor_fixo')",
            name="ck_reajuste_tipo",
        ),
        Index("idx_reajuste_data", "executado_em"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=False
    )
    tipo_reajuste: Mapped[str] = mapped_column(String(12), nullable=False)
    valor_reajuste: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    criterio: Mapped[str] = mapped_column(Text, nullable=False)
    itens_afetados: Mapped[int] = mapped_column(Integer, nullable=False)
    detalhes: Mapped[list] = mapped_column(JSONB, nullable=False)
    executado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PrecoParametro(Base):
    """Parâmetro global de precificação da filial (M1, PRD v3.0 §3.2.1).

    Chaves previstas: `acrescimo_fornecedor_pct` (130) e `markup_orcamento_pct`
    (6) — os valores default moram em `precificacao.PARAMETROS_PADRAO`; a linha
    só existe quando alguém altera. `usuario_id` registra quem mudou e
    `atualizado_em` quando (NFR de rastreabilidade).
    """

    __tablename__ = "preco_parametro"
    __table_args__ = (
        UniqueConstraint("filial_id", "chave", name="uq_preco_parametro_filial_chave"),
        CheckConstraint("valor >= 0", name="ck_preco_parametro_valor"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    chave: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )