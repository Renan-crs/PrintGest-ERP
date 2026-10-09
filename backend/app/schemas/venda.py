"""Schemas Pydantic da Venda de Balcão (PDV) — PRD v2.0 §2.2 fluxo Balcão.

Esquemas de entrada (`VendaCreate`/`VendaItemIn`) e saída (`VendaOut`/
`VendaItemOut`). Valores monetários como `Decimal`; a saída agrega nomes de
cliente/vendedor/operador e os itens da venda.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import FormaPagamento, StatusVenda
from app.schemas.common import ORMModel


class VendaItemIn(BaseModel):
    produto_id: int | None = Field(default=None)
    descricao_avulsa: str | None = Field(default=None, max_length=255)
    quantidade: Decimal = Field(default=Decimal("1"), gt=0)
    valor_unitario: Decimal = Field(default=Decimal("0"), ge=0)
    desconto: Decimal = Field(default=Decimal("0"), ge=0)


class VendaCreate(BaseModel):
    cliente_id: int | None = None
    vendedor_id: int | None = None
    data_venda: date = Field(default_factory=date.today)
    desconto: Decimal = Field(default=Decimal("0"), ge=0)
    forma_pagamento: FormaPagamento
    parcelas: int = Field(default=1, ge=1)
    observacoes: str | None = None
    # Confirmação do recebimento antecipado (exigido pelo cliente, quando houver).
    pagamento_confirmado: bool = False
    itens: list[VendaItemIn] = Field(min_length=1)


class VendaItemOut(ORMModel):
    id: int
    seq: int
    produto_id: int | None = None
    descricao_avulsa: str | None = None
    quantidade: Decimal
    valor_unitario: Decimal
    desconto: Decimal
    valor_total: Decimal


class VendaOut(ORMModel):
    id: int
    filial_id: int
    numero: int
    status: StatusVenda
    cliente_id: int | None = None
    cliente_nome: str | None = None
    vendedor_id: int | None = None
    vendedor_nome: str | None = None
    operador_caixa: int | None = None
    operador_caixa_nome: str | None = None
    data_venda: date
    valor_itens: Decimal
    desconto: Decimal
    valor_total: Decimal
    forma_pagamento: FormaPagamento
    parcelas: int
    caixa_id: int | None = None
    documento_fiscal_id: int | None = None
    observacoes: str | None = None
    criado_por: int | None = None
    created_at: datetime
    updated_at: datetime
    itens: list[VendaItemOut] = []