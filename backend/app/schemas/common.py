"""Modelos Pydantic transversais: paginação e envelope de resposta padrão.

Convenção de resposta da API:
  - Listagens -> {"data": [...], "meta": {"total", "limit", "offset"}}
  - Recurso    -> {"data": {...}}
  - Erro       -> HTTPException com "detail" em PT-BR
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class MetaPaginacao(BaseModel):
    total: int
    limit: int
    offset: int


class ListaResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: MetaPaginacao


class ItemResponse(BaseModel, Generic[T]):
    data: T


class ORMModel(BaseModel):
    """Base para schemas que convertem direto de objetos SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)