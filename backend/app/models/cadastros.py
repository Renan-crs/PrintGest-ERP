from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CHAR,
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
    OrigemMov,
    TipoMovEstoque,
    TipoPessoa,
    TipoProduto,
    pg_enum,
)


from decimal import Decimal

class Cliente(Base):
    __tablename__ = "cliente"
    __table_args__ = (
        # Um cliente exige (no máximo) uma condição de pagamento antecipado: o
        # total adiantado ou um sinal percentual — nunca os dois.
        CheckConstraint(
            "NOT (pagamento_adiantado AND sinal)",
            name="ck_cliente_adiantamento_exclusivo",
        ),
        CheckConstraint("sinal_pct BETWEEN 0 AND 100", name="ck_cliente_sinal_pct"),
        Index("idx_cliente_nome", "nome_razao"),
        Index(
            "idx_cliente_dt_nas",
            "data_nascimento",
            postgresql_where=text("data_nascimento IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    nome_razao: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_pessoa: Mapped[TipoPessoa] = mapped_column(
        pg_enum(TipoPessoa), nullable=False, server_default=TipoPessoa.PF.value
    )
    cpf_cnpj: Mapped[str | None] = mapped_column(String(18), unique=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20))
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    email: Mapped[str | None] = mapped_column(String(120))
    telefone: Mapped[str | None] = mapped_column(String(20))
    celular: Mapped[str | None] = mapped_column(String(20))
    logradouro: Mapped[str | None] = mapped_column(String(160))
    numero: Mapped[str | None] = mapped_column(String(12))
    complemento: Mapped[str | None] = mapped_column(String(80))
    bairro: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    cep: Mapped[str | None] = mapped_column(CHAR(8))
    foto_path: Mapped[str | None] = mapped_column(String(500))
    observacoes: Mapped[str | None] = mapped_column(Text)
    # Condição de pagamento antecipado exigida do cliente (PRD tela 2.1):
    # `pagamento_adiantado` = 100% na abertura da OS/venda; `sinal` = percentual
    # informado em `sinal_pct`. Mutuamente exclusivos (CHECK).
    pagamento_adiantado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    sinal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    sinal_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default="50"
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Fornecedor(Base):
    __tablename__ = "fornecedor"
    __table_args__ = (Index("idx_fornecedor_nome", "nome_razao"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    nome_razao: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_pessoa: Mapped[TipoPessoa] = mapped_column(
        pg_enum(TipoPessoa), nullable=False, server_default=TipoPessoa.PJ.value
    )
    cpf_cnpj: Mapped[str | None] = mapped_column(String(18), unique=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    telefone: Mapped[str | None] = mapped_column(String(20))
    celular: Mapped[str | None] = mapped_column(String(20))
    contato_nome: Mapped[str | None] = mapped_column(String(120))
    logradouro: Mapped[str | None] = mapped_column(String(160))
    numero: Mapped[str | None] = mapped_column(String(12))
    complemento: Mapped[str | None] = mapped_column(String(80))
    bairro: Mapped[str | None] = mapped_column(String(80))
    cidade: Mapped[str | None] = mapped_column(String(80))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    cep: Mapped[str | None] = mapped_column(CHAR(8))
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Funcionario(Base):
    __tablename__ = "funcionario"
    __table_args__ = (
        CheckConstraint(
            "comissao_pct BETWEEN 0 AND 100", name="ck_funcionario_comissao"
        ),
        Index("idx_funcionario_nome", "nome"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cpf: Mapped[str | None] = mapped_column(String(18), unique=True)
    cargo: Mapped[str | None] = mapped_column(String(60))
    email: Mapped[str | None] = mapped_column(String(120))
    telefone: Mapped[str | None] = mapped_column(String(20))
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    data_admissao: Mapped[date | None] = mapped_column(Date)
    e_vendedor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    e_atendente: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    e_producao: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    comissao_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), server_default="0")
    observacoes: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # M3 (§3.10): link com usuário de login
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    usuario: Mapped["Usuario | None"] = relationship(
        back_populates="funcionario",
        foreign_keys=[usuario_id]
    )


class ProdutoCategoria(Base):
    __tablename__ = "produto_categoria"
    __table_args__ = (
        UniqueConstraint("filial_id", "nome", name="uq_produto_categoria_filial_nome"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (
        CheckConstraint(
            "preco_custo >= 0 AND preco_venda >= 0", name="ck_produto_precos"
        ),
        CheckConstraint("estoque_minimo >= 0", name="ck_produto_estoque_minimo"),
        Index("idx_produto_nome", "nome"),
        Index("idx_produto_categoria", "categoria_id"),
        Index("idx_produto_codigo_busca", "codigo"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    categoria_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("produto_categoria.id")
    )
    codigo: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    codigo_barras: Mapped[str | None] = mapped_column(String(30))
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    tipo: Mapped[TipoProduto] = mapped_column(
        pg_enum(TipoProduto), nullable=False, server_default=TipoProduto.PRODUTO.value
    )
    unidade: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="un"
    )
    controla_estoque: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    preco_custo: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    preco_venda: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    estoque_minimo: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default="0"
    )
    dimensoes: Mapped[str | None] = mapped_column(String(40))
    foto1_path: Mapped[str | None] = mapped_column(String(500))
    foto2_path: Mapped[str | None] = mapped_column(String(500))
    bloqueado_reajuste: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    categoria: Mapped[ProdutoCategoria | None] = relationship()


class ProdutoEstoque(Base):
    __tablename__ = "produto_estoque"
    __table_args__ = (
        Index("idx_estoque_produto", "produto_id", "filial_id"),
        UniqueConstraint("filial_id", "produto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id"), nullable=False
    )
    saldo: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default="0"
    )
    reservado: Mapped[Decimal] = mapped_column(
        Numeric(12, 3), nullable=False, server_default="0"
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MovimentoEstoque(Base):
    __tablename__ = "movimento_estoque"
    __table_args__ = (
        Index("idx_kardex_produto", "produto_id", text("criado_em DESC")),
        Index("idx_kardex_origem", "origem", "documento_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id"), nullable=False
    )
    tipo: Mapped[TipoMovEstoque] = mapped_column(pg_enum(TipoMovEstoque), nullable=False)
    origem: Mapped[OrigemMov] = mapped_column(pg_enum(OrigemMov), nullable=False)
    documento_id: Mapped[int | None] = mapped_column(BigInteger)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    saldo_anterior: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    saldo_posterior: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(255))
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )