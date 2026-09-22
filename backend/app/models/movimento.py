from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
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
from app.models.cadastros import Cliente, Funcionario
from app.models.enums import (
    FormaPagamento,
    StatusAgenda,
    StatusOs,
    StatusPedido,
    StatusVenda,
    TipoAgenda,
    TipoOs,
    pg_enum,
)


class OrdemServico(Base):
    __tablename__ = "ordem_servico"
    __table_args__ = (
        CheckConstraint(
            "orcamento_origem_id IS NULL OR orcamento_origem_id <> id",
            name="ck_os_origem_nao_self",
        ),
        CheckConstraint(
            "desconto >= 0 AND valor_itens >= 0 AND valor_total >= 0",
            name="ck_os_valores_nao_negativos",
        ),
        CheckConstraint(
            "valor_itens - desconto = valor_total",
            name="ck_os_valor_consistente",
        ),
        Index("idx_os_status", "status", "data_emissao"),
        Index("idx_os_cliente", "cliente_id"),
        Index("idx_os_numero", "filial_id", "numero"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    numero: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("nextval('seq_os_numero')"),
    )
    tipo: Mapped[TipoOs] = mapped_column(
        pg_enum(TipoOs), nullable=False, server_default=TipoOs.OS.value
    )
    status: Mapped[StatusOs] = mapped_column(
        pg_enum(StatusOs), nullable=False, server_default=StatusOs.ABERTO.value
    )
    orcamento_origem_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ordem_servico.id")
    )
    cliente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cliente.id"))
    vendedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("funcionario.id")
    )
    atendente_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("funcionario.id")
    )
    data_emissao: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    data_previsao_entrega: Mapped[date | None] = mapped_column(Date)
    data_conclusao: Mapped[date | None] = mapped_column(Date)
    data_entrega: Mapped[date | None] = mapped_column(Date)
    desconto: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    valor_itens: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    forma_pagamento: Mapped[FormaPagamento | None] = mapped_column(
        pg_enum(FormaPagamento)
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    cliente: Mapped[Cliente | None] = relationship(foreign_keys=[cliente_id])
    vendedor: Mapped[Funcionario | None] = relationship(
        foreign_keys=[vendedor_id]
    )
    atendente: Mapped[Funcionario | None] = relationship(
        foreign_keys=[atendente_id]
    )
    itens: Mapped[list["OrdemServicoItem"]] = relationship(
        back_populates="os",
        cascade="all, delete-orphan",
        order_by="OrdemServicoItem.seq",
    )


class OrdemServicoItem(Base):
    __tablename__ = "ordem_servico_item"
    __table_args__ = (
        UniqueConstraint("ordem_servico_id", "seq"),
        CheckConstraint("quantidade > 0", name="ck_os_item_qtd_positiva"),
        CheckConstraint(
            "valor_unitario >= 0 AND desconto >= 0 AND valor_total >= 0",
            name="ck_os_item_valores_nao_negativos",
        ),
        Index("idx_os_item_produto", "produto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ordem_servico_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ordem_servico.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    produto_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("produto.id"))
    descricao_avulsa: Mapped[str | None] = mapped_column(String(255))
    quantidade: Mapped[float] = mapped_column(Numeric(12, 3), server_default="1")
    dimensoes: Mapped[str | None] = mapped_column(String(40))
    valor_unitario: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    desconto: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    executado: Mapped[bool] = mapped_column(Boolean, server_default="false")

    os: Mapped[OrdemServico] = relationship(back_populates="itens")


class VendaBalcao(Base):
    __tablename__ = "venda_balcao"
    __table_args__ = (
        CheckConstraint(
            "status <> 'ok' OR operador_caixa IS NOT NULL",
            name="ck_venda_operador",
        ),
        CheckConstraint(
            "desconto >= 0 AND valor_itens >= 0 AND valor_total >= 0",
            name="ck_venda_valores_nao_negativos",
        ),
        CheckConstraint(
            "valor_itens - desconto = valor_total",
            name="ck_venda_valor_consistente",
        ),
        CheckConstraint("parcelas >= 1", name="ck_venda_parcelas"),
        Index("idx_venda_status", "status", "data_venda"),
        Index("idx_venda_cliente", "cliente_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    numero: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("nextval('seq_venda_numero')"),
    )
    status: Mapped[StatusVenda] = mapped_column(
        pg_enum(StatusVenda), nullable=False, server_default=StatusVenda.OK.value
    )
    cliente_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cliente.id"))
    vendedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("funcionario.id")
    )
    operador_caixa: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    data_venda: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    valor_itens: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    desconto: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    forma_pagamento: Mapped[FormaPagamento] = mapped_column(
        pg_enum(FormaPagamento), nullable=False
    )
    parcelas: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    caixa_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("caixa.id"))
    documento_fiscal_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documento_fiscal.id")
    )
    observacoes: Mapped[str | None] = mapped_column(Text)
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    itens: Mapped[list["VendaBalcaoItem"]] = relationship(back_populates="venda")


class VendaBalcaoItem(Base):
    __tablename__ = "venda_balcao_item"
    __table_args__ = (
        UniqueConstraint("venda_balcao_id", "seq"),
        CheckConstraint("quantidade > 0", name="ck_venda_item_qtd_positiva"),
        CheckConstraint(
            "valor_unitario >= 0 AND desconto >= 0 AND valor_total >= 0",
            name="ck_venda_item_valores_nao_negativos",
        ),
        Index("idx_venda_item_produto", "produto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    venda_balcao_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("venda_balcao.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    produto_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("produto.id"))
    descricao_avulsa: Mapped[str | None] = mapped_column(String(255))
    quantidade: Mapped[float] = mapped_column(Numeric(12, 3), server_default="1")
    valor_unitario: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    desconto: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")

    venda: Mapped[VendaBalcao] = relationship(back_populates="itens")


class PedidoCompra(Base):
    __tablename__ = "pedido_compra"
    __table_args__ = (
        CheckConstraint("valor_total >= 0", name="ck_pedido_valor_total"),
        Index("idx_pedido_status", "status", "data_pedido"),
        Index("idx_pedido_fornecedor", "fornecedor_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    numero: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("nextval('seq_pedido_numero')"),
    )
    status: Mapped[StatusPedido] = mapped_column(
        pg_enum(StatusPedido), nullable=False, server_default=StatusPedido.ABERTO.value
    )
    fornecedor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("fornecedor.id")
    )
    data_pedido: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    previsao_entrega: Mapped[date | None] = mapped_column(Date)
    data_recebimento: Mapped[date | None] = mapped_column(Date)
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    observacoes: Mapped[str | None] = mapped_column(Text)
    solicitante_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    itens: Mapped[list["PedidoCompraItem"]] = relationship(back_populates="pedido")


class PedidoCompraItem(Base):
    __tablename__ = "pedido_compra_item"
    __table_args__ = (
        UniqueConstraint("pedido_compra_id", "seq"),
        CheckConstraint("quantidade > 0", name="ck_pedido_item_qtd_positiva"),
        CheckConstraint(
            "quantidade_recebida BETWEEN 0 AND quantidade",
            name="ck_pedido_item_qtd_recebida",
        ),
        CheckConstraint(
            "valor_unitario >= 0 AND valor_total >= 0",
            name="ck_pedido_item_valores_nao_negativos",
        ),
        Index("idx_pedido_item_produto", "produto_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pedido_compra_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("pedido_compra.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    produto_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("produto.id"), nullable=False
    )
    descricao_avulsa: Mapped[str | None] = mapped_column(String(255))
    quantidade: Mapped[float] = mapped_column(Numeric(12, 3), server_default="1")
    quantidade_recebida: Mapped[float] = mapped_column(Numeric(12, 3), server_default="0")
    valor_unitario: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[float] = mapped_column(Numeric(14, 2), server_default="0")

    pedido: Mapped[PedidoCompra] = relationship(back_populates="itens")


class Agendamento(Base):
    __tablename__ = "agendamento"
    __table_args__ = (
        CheckConstraint(
            "data_hora_fim IS NULL OR data_hora_fim > data_hora_inicio",
            name="ck_agendamento_horario",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filial_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("filial.id"), nullable=False
    )
    tipo: Mapped[TipoAgenda] = mapped_column(
        pg_enum(TipoAgenda), nullable=False, server_default=TipoAgenda.PRODUCAO.value
    )
    status: Mapped[StatusAgenda] = mapped_column(
        pg_enum(StatusAgenda), nullable=False, server_default=StatusAgenda.AGENDADO.value
    )
    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    data_hora_inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    data_hora_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ordem_servico_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ordem_servico.id")
    )
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )