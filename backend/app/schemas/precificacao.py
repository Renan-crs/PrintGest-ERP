"""Schemas de regra de preço — compartilhados pelo simulador e pelos documentos.

A regra viaja no payload enquanto `tabela_preco`/`regra_preco` não são
persistidas (Fase V1). Nenhum campo é obrigatório: sem regra, venda/OS mantêm
o comportamento legado de aceitar `valor_unitario` do cliente.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

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


# ----------------------------------------------------------- persistência V1


class TabelaPrecoCreate(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    cliente_id: int | None = None
    padrao: bool = False


class TabelaPrecoOut(ORMModel):
    id: int
    uuid: str | None = None
    filial_id: int
    cliente_id: int | None = None
    nome: str
    padrao: bool
    ativo: bool


class RegraPrecoCreate(RegraPrecoIn):
    produto_id: int = Field(gt=0)
    tabela_preco_id: int = Field(gt=0)
    vigencia_inicio: datetime | None = None
    vigencia_fim: datetime | None = None
    prioridade: int = Field(default=0, ge=0)


class RegraPrecoOut(ORMModel):
    id: int
    uuid: str | None = None
    tabela_preco_id: int
    produto_id: int
    preco_base: Decimal
    faixas: list[FaixaPrecoIn] = Field(default_factory=list)
    modificadores: list[ModificadorIn] = Field(default_factory=list)
    minimo: Decimal | None = None
    modo_faixa: MODO_FAIXA = "TODA_A_QUANTIDADE"
    vigencia_inicio: datetime
    vigencia_fim: datetime | None
    prioridade: int
    ativo: bool
