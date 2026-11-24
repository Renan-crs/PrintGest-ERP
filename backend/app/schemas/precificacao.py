"""Schemas de regra de preço — compartilhados pelo simulador e pelos documentos.

A regra viaja no payload enquanto `tabela_preco`/`regra_preco` não são
persistidas (Fase V1). Nenhum campo é obrigatório: sem regra, venda/OS mantêm
o comportamento legado de aceitar `valor_unitario` do cliente.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

MODO_FAIXA = Literal["TODA_A_QUANTIDADE", "PROGRESSIVA"]
TIPO_MODIFICADOR = Literal[
    "MULTIPLICADOR", "ACRESCIMO_UNITARIO", "ACRESCIMO_FIXO"
]


class FaixaPrecoIn(BaseModel):
    qtd_min: int = Field(ge=1)
    qtd_max: int | None = Field(default=None, ge=1)
    preco_unitario: Decimal = Field(default=Decimal("0"), ge=0)


class ModificadorIn(BaseModel):
    tipo: TIPO_MODIFICADOR
    valor: Decimal
    descricao: str | None = None


class RegraPrecoIn(BaseModel):
    preco_base: Decimal = Field(default=Decimal("0"), ge=0)
    faixas: list[FaixaPrecoIn] = Field(default_factory=list)
    modificadores: list[ModificadorIn] = Field(default_factory=list)
    minimo: Decimal | None = Field(default=None, ge=0)
    modo_faixa: MODO_FAIXA = "TODA_A_QUANTIDADE"
