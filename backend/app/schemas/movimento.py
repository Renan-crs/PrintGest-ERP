"""Schemas Pydantic do movimento — Ordem de Serviço e Orçamento (Fase 2).

Orçamento e OS vivem na mesma tabela `ordem_servico`, diferenciados por `tipo`
(`orcamento`/`os`). A conversão cria um novo registro `os` que referencia o
orçamento via `orcamento_origem_id` e marca o original como `convertido`.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    FormaPagamento,
    StatusOs,
    StatusVenda,
    TipoOs,
)
from app.schemas.common import ORMModel


class OsItemIn(BaseModel):
    produto_id: int | None = Field(default=None)
    descricao_avulsa: str | None = Field(default=None, max_length=255)
    quantidade: Decimal = Field(default=Decimal("1"), gt=0)
    dimensoes: str | None = Field(default=None, max_length=40)
    valor_unitario: Decimal = Field(default=Decimal("0"), ge=0)
    desconto: Decimal = Field(default=Decimal("0"), ge=0)

    @model_validator(mode="after")
    def _item_requer_referencia(self) -> "OsItemIn":
        if not self.produto_id and not (self.descricao_avulsa or "").strip():
            raise ValueError(
                "Cada item precisa de um produto (produto_id) ou de uma descrição avulsa."
            )
        return self


class OsCreate(BaseModel):
    tipo: TipoOs = TipoOs.OS
    cliente_id: int
    vendedor_id: int | None = None
    atendente_id: int | None = None
    data_previsao_entrega: date | None = None
    desconto: Decimal = Field(default=Decimal("0"), ge=0)
    forma_pagamento: FormaPagamento | None = None
    observacoes: str | None = None
    itens: list[OsItemIn] = Field(min_length=1)


class OsUpdate(BaseModel):
    """Atualização parcial — só aplica campos enviados (exclude_unset)."""

    cliente_id: int | None = None
    vendedor_id: int | None = None
    atendente_id: int | None = None
    data_previsao_entrega: date | None = None
    desconto: Decimal | None = Field(default=None, ge=0)
    forma_pagamento: FormaPagamento | None = None
    observacoes: str | None = None
    itens: list[OsItemIn] | None = None


class OsStatusIn(BaseModel):
    status: StatusOs


class OsItemOut(ORMModel):
    id: int
    seq: int
    produto_id: int | None = None
    descricao_avulsa: str | None = None
    quantidade: Decimal
    dimensoes: str | None = None
    valor_unitario: Decimal
    desconto: Decimal
    valor_total: Decimal
    executado: bool


class OsOut(ORMModel):
    id: int
    filial_id: int
    numero: int
    tipo: TipoOs
    status: StatusOs
    orcamento_origem_id: int | None = None
    cliente_id: int | None = None
    cliente_nome: str | None = None
    vendedor_id: int | None = None
    vendedor_nome: str | None = None
    atendente_id: int | None = None
    atendente_nome: str | None = None
    data_emissao: date
    data_previsao_entrega: date | None = None
    data_conclusao: date | None = None
    data_entrega: date | None = None
    desconto: Decimal
    valor_itens: Decimal
    valor_total: Decimal
    forma_pagamento: FormaPagamento | None = None
    observacoes: str | None = None
    criado_por: int | None = None
    created_at: datetime
    updated_at: datetime
    itens: list[OsItemOut] = []