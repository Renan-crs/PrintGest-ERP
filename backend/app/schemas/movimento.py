"""Schemas Pydantic do movimento — Ordem de Serviço e Orçamento (Fase 2).

Orçamento e OS vivem na mesma tabela `ordem_servico`, diferenciados por `tipo`
(`orcamento`/`os`). A conversão cria um novo registro `os` que referencia o
orçamento via `orcamento_origem_id` e marca o original como `convertido`.
"""

from datetime import date, datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import (
    FormaPagamento,
    StatusOs,
    StatusVenda,
    TipoItemOs,
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
    # M1 (PRD v3.0 §3.2.2): item próprio ou serviço de fornecedor. Item de
    # fornecedor nasce "Aguardando cotação" (valor 0) até a cotação selecionada.
    tipo: TipoItemOs = TipoItemOs.PROPRIO

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
    # Confirmação do recebimento antecipado (exigido pelo cliente, quando houver).
    pagamento_confirmado: bool = False
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


class OsConverterIn(BaseModel):
    """Corpo opcional da conversão de orçamento em O.S."""

    pagamento_confirmado: bool = False


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
    tipo: TipoItemOs = TipoItemOs.PROPRIO
    # Derivado do tipo + cotações: 'aguardando' | 'cotado' | None (próprio).
    # NÃO expõe VF/CP/snapshot — isso é informação interna (§3.2.3), disponível
    # apenas nas rotas de cotação para quem tem `ver_custo_terceiro`.
    estado_cotacao: str | None = None


class ConferenciaTerceirizadoIn(BaseModel):
    """Conferência de qualidade do item terceirizado (§3.6)."""

    conferencia: Literal["ok", "refacao"]
    observacoes: str | None = None


class RecebimentoTerceirizadoIn(BaseModel):
    """Retorno do fornecedor (§3.6). Data vazia = hoje."""

    data_retorno: date | None = None


class CotacaoIn(BaseModel):
    """Lançamento de cotação de fornecedor para um item terceirizado."""

    fornecedor_id: int
    vf: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    validade: date | None = None
    prazo_dias: int | None = Field(default=None, ge=0)
    observacoes: str | None = None
    # Seleciona já no lançamento (única selecionada do item).
    selecionada: bool = False


class CotacaoOut(BaseModel):
    """Cotação no comparativo interno — VF é gated por `ver_custo_terceiro`.

    A resposta omite o campo para perfis sem permissão; quem lança sem a
    permissão vê o VF só enquanto digita (aqui ele é Admin/Gerente).
    """

    id: int
    fornecedor_id: int
    fornecedor_nome: str | None = None
    vf: Decimal | None = None
    validade: date | None = None
    prazo_dias: int | None = None
    observacoes: str | None = None
    selecionada: bool = False
    criado_em: datetime



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