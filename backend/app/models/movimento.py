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
from app.models.cadastros import Cliente, Fornecedor, Funcionario
from app.models.core import Usuario
from app.models.enums import (
    FormaPagamento,
    StatusAgenda,
    StatusOs,
    StatusPedido,
    StatusVenda,
    TipoAgenda,
    TipoItemOs,
    TipoOs,
    pg_enum,
)
from sqlalchemy.dialects.postgresql import JSONB


from decimal import Decimal

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
    desconto: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    valor_itens: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
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
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default="1")
    dimensoes: Mapped[str | None] = mapped_column(String(40))
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    desconto: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    executado: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # M1 (PRD v3.0 §3.2.2): item de fornecedor terceirizado + snapshot do cálculo
    # aplicado (VF, percentuais, CP, VO) — gravado quando a cotação é selecionada;
    # mudar os parâmetros globais depois não altera este item (§3.2.1).
    tipo: Mapped[TipoItemOs] = mapped_column(
        pg_enum(TipoItemOs), nullable=False, server_default=TipoItemOs.PROPRIO.value
    )
    snapshot_preco: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    os: Mapped[OrdemServico] = relationship(back_populates="itens")
    cotacoes: Mapped[list["OrdemServicoItemCotacao"]] = relationship(
        back_populates="item",
        order_by="OrdemServicoItemCotacao.criado_em",
        cascade="all, delete-orphan",
    )


class OrdemServicoItemCotacao(Base):
    """Cotação de fornecedor para um item terceirizado (PRD v3.0 §3.2.2).

    Várias cotações podem existir; **uma** é marcada `selecionada` e só ela
    compõe o orçamento (o `valor_unitario` do item assume o VO calculado).
    VF/cálculo são informação interna: a API omite esses campos para perfis
    sem `ver_custo_terceiro` (Admin/Gerente — §3.2.3).
    """

    __tablename__ = "os_item_cotacao"
    __table_args__ = (
        CheckConstraint("vf >= 0", name="ck_os_item_cotacao_vf"),
        CheckConstraint(
            "prazo_dias IS NULL OR prazo_dias >= 0", name="ck_os_item_cotacao_prazo"
        ),
        Index("idx_os_item_cotacao_item", "item_id"),
        # Só UMA cotação selecionada por item (PRD §3.2.2 item 5).
        Index(
            "uq_os_item_cotacao_selecionada",
            "item_id",
            unique=True,
            postgresql_where=text("selecionada"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ordem_servico_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    fornecedor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fornecedor.id"), nullable=False
    )
    vf: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    validade: Mapped[date | None] = mapped_column(Date, nullable=True)
    prazo_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observacoes: Mapped[str | None] = mapped_column(Text)
    anexo_path: Mapped[str | None] = mapped_column(String(500))
    selecionada: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # M1 (§3.2.2 item 7): item do pedido de compra gerado na aprovação do
    # orçamento — carrega o VF cotado para este fornecedor.
    pedido_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pedido_compra_item.id")
    )
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    item: Mapped[OrdemServicoItem] = relationship(back_populates="cotacoes")
    fornecedor: Mapped["Fornecedor"] = relationship(lazy="joined")


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
    valor_itens: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    desconto: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
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

    cliente: Mapped[Cliente | None] = relationship(foreign_keys=[cliente_id])
    vendedor: Mapped[Funcionario | None] = relationship(foreign_keys=[vendedor_id])
    operador: Mapped[Usuario | None] = relationship(foreign_keys=[operador_caixa])


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
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default="1")
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    desconto: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")

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
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    observacoes: Mapped[str | None] = mapped_column(Text)
    solicitante_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("usuario.id")
    )
    # M1 (§3.2.2 item 7): OS que gerou este pedido na aprovação do orçamento.
    os_origem_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ordem_servico.id")
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
    # M1 (§3.2.2): serviço terceirizado não tem produto no catálogo — a
    # descrição vive em `descricao_avulsa` (produto NULO nesses casos).
    produto_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("produto.id")
    )
    descricao_avulsa: Mapped[str | None] = mapped_column(String(255))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default="1")
    quantidade_recebida: Mapped[Decimal] = mapped_column(Numeric(12, 3), server_default="0")
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), server_default="0")

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