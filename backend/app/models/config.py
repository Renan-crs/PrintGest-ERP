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
    """Parâmetro de precificação (M1 global / M2 sobrescrita por fornecedor).

    Chaves previstas: `acrescimo_fornecedor_pct` (130) e `markup_orcamento_pct`
    (6) — os valores default moram em `precificacao.PARAMETROS_PADRAO`.

    **Escopo (M2, Q-04):** `fornecedor_id = NULL` = parâmetro global da filial;
    `fornecedor_id = X` = sobrescrita que vale apenas para cotações daquele
    fornecedor (precedência: fornecedor > global > default). `usuario_id`
    registra quem mudou e `atualizado_em` quando (NFR de rastreabilidade).
    """

    __tablename__ = "preco_parametro"
    __table_args__ = (
        # Uma linha por (filial, chave) quando global; por (filial, fornecedor,
        # chave) quando é sobrescrita — o índice parcial permite os dois.
        Index(
            "uq_preco_parametro_escopo",
            "filial_id",
            "fornecedor_id",
            "chave",
            unique=True,
        ),
        CheckConstraint("valor >= 0", name="ck_preco_parametro_valor"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    fornecedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fornecedor.id"), nullable=True
    )
    chave: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=True
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )