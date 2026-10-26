from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    StatusCaixa,
    StatusConta,
    TipoMovCaixa,
    TipoPlanoConta,
    pg_enum,
)


from decimal import Decimal

class PlanoContas(Base):
    __tablename__ = "plano_contas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    tipo: Mapped[TipoPlanoConta] = mapped_column(
        pg_enum(TipoPlanoConta), nullable=False
    )
    pai_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("plano_contas.id"))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    __table_args__ = (
        UniqueConstraint("filial_id", "codigo"),
        Index("idx_plano_pai", "pai_id"),
    )


class ContaReceber(Base):
    __tablename__ = "conta_receber"
    __table_args__ = (
        CheckConstraint(
            "valor >= 0 AND valor_pago >= 0", name="ck_cr_valores_nao_negativos"
        ),
        CheckConstraint(
            "parcela >= 1 AND total_parcelas >= 1", name="ck_cr_parcelas"
        ),
        Index("idx_cr_vencimento", "status", "vencimento"),
        Index("idx_cr_cliente", "cliente_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    cliente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cliente.id"))
    plano_conta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plano_contas.id")
    )
    venda_balcao_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("venda_balcao.id")
    )
    ordem_servico_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ordem_servico.id")
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    parcela: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    total_parcelas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valor_pago: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    status: Mapped[StatusConta] = mapped_column(
        pg_enum(StatusConta), nullable=False, server_default=StatusConta.ABERTA.value
    )
    data_pagamento: Mapped[date | None] = mapped_column(Date)
    usuario_baixa_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ContaPagar(Base):
    __tablename__ = "conta_pagar"
    __table_args__ = (
        CheckConstraint(
            "valor >= 0 AND valor_pago >= 0", name="ck_cp_valores_nao_negativos"
        ),
        CheckConstraint(
            "parcela >= 1 AND total_parcelas >= 1", name="ck_cp_parcelas"
        ),
        Index("idx_cp_vencimento", "status", "vencimento"),
        Index("idx_cp_fornecedor", "fornecedor_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    fornecedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fornecedor.id")
    )
    plano_conta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("plano_contas.id")
    )
    pedido_compra_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pedido_compra.id")
    )
    descricao: Mapped[str] = mapped_column(String(255), nullable=False)
    parcela: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    total_parcelas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valor_pago: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    status: Mapped[StatusConta] = mapped_column(
        pg_enum(StatusConta), nullable=False, server_default=StatusConta.ABERTA.value
    )
    data_pagamento: Mapped[date | None] = mapped_column(Date)
    usuario_baixa_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Caixa(Base):
    __tablename__ = "caixa"
    __table_args__ = (
        CheckConstraint(
            "valor_abertura >= 0", name="ck_caixa_valor_abertura"
        ),
        Index("idx_caixa_status", "status", "data_abertura"),
        Index(
            "uq_caixa_aberto_filial_usuario",
            "filial_id",
            "usuario_id",
            unique=True,
            postgresql_where=text("status = 'aberto'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    usuario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("usuario.id"), nullable=False
    )
    status: Mapped[StatusCaixa] = mapped_column(
        pg_enum(StatusCaixa), nullable=False, server_default=StatusCaixa.ABERTO.value
    )
    data_abertura: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valor_abertura: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    data_fechamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valor_esperado: Mapped[float | None] = mapped_column(Numeric(14, 2))
    valor_informado: Mapped[float | None] = mapped_column(Numeric(14, 2))
    diferenca: Mapped[float | None] = mapped_column(Numeric(14, 2))
    observacoes: Mapped[str | None] = mapped_column(Text)
    closed_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    movimentos: Mapped[list["MovimentoCaixa"]] = relationship(back_populates="caixa")


class MovimentoCaixa(Base):
    __tablename__ = "movimento_caixa"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caixa_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("caixa.id"), nullable=False
    )
    tipo: Mapped[TipoMovCaixa] = mapped_column(pg_enum(TipoMovCaixa), nullable=False)
    venda_balcao_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("venda_balcao.id")
    )
    conta_receber_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("conta_receber.id")
    )
    conta_pagar_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("conta_pagar.id")
    )
    descricao: Mapped[str | None] = mapped_column(String(255))
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint("valor >= 0", name="ck_movcaixa_valor"),
        Index("idx_movcaixa_caixa", "caixa_id", "criado_em"),
    )

    caixa: Mapped[Caixa] = relationship(back_populates="movimentos")