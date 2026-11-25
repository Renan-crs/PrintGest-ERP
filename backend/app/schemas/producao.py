"""Schemas de ficha de consumo e baixa de produção (guia V2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class FichaConsumoIn(BaseModel):
    produto_id: int = Field(gt=0)
    insumo_id: int = Field(gt=0)
    quantidade_por_unidade: Decimal = Field(gt=0)
    perda_percentual: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    custo_processo_unitario: Decimal = Field(default=Decimal("0"), ge=0)
    vigencia_inicio: datetime | None = None
    vigencia_fim: datetime | None = None

    @model_validator(mode="after")
    def _insumo_diferente_do_produto(self) -> "FichaConsumoIn":
        if self.insumo_id == self.produto_id:
            raise ValueError("O insumo não pode ser o próprio produto.")
        return self


class FichaConsumoOut(ORMModel):
    id: int
    uuid: str | None = None
    filial_id: int
    produto_id: int
    insumo_id: int
    quantidade_por_unidade: Decimal
    perda_percentual: Decimal
    custo_processo_unitario: Decimal
    vigencia_inicio: datetime
    vigencia_fim: datetime | None
    ativo: bool


class BaixarConsumoIn(BaseModel):
    """Baixa real; ausência de `quantidades` usa o valor previsto de cada insumo."""

    quantidades: dict[int, Decimal] | None = Field(default=None)
    motivo_perda: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _quantidades_validas(self) -> "BaixarConsumoIn":
        if self.quantidades and any(q < 0 for q in self.quantidades.values()):
            raise ValueError("Quantidades não podem ser negativas.")
        return self


class ConsumoOut(ORMModel):
    id: int
    filial_id: int
    ordem_servico_item_id: int
    insumo_id: int
    quantidade_prevista: Decimal
    quantidade_real: Decimal
    ficha_consumo_id: int | None = None
    custo_unitario_previsto: Decimal | None = None
    baixado_em: datetime | None = None
    baixado_por: int | None = None
    motivo_perda: str | None = None


class CustoServicoOut(BaseModel):
    """Custo unitário, margem bruta e consumo previsto calculados (RF-VR-17)."""

    custo_unitario: Decimal
    margem_bruta: Decimal | None
    consumo_previsto: list[dict[str, Any]] = Field(default_factory=list)
    alertas: list[str] = Field(default_factory=list)
