"""CRUD genérico para as telas de cadastro — listagem com busca rápida e paginação.

Busca textual é sempre aplicada sobre colunas indexadas (ver models), com ILIKE —
padrão exigido pelas listas do sistema (busca rápida por código/nome/documento).
"""

from typing import Any, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base

ModelT = TypeVar("ModelT", bound=Base)


def _pagina(db: Session, model: type[ModelT], *, filial_id: int | None = None) -> Any:
    """Query base: apenas registros ativos da filial efetiva (D5: multiprovisão por filial)."""
    query = db.query(model)
    if filial_id is not None and hasattr(model, "filial_id"):
        query = query.filter(model.filial_id == filial_id)
    if hasattr(model, "ativo"):
        query = query.filter(model.ativo.is_(True))
    return query


def listar(
    db: Session,
    model: type[ModelT],
    *,
    filial_id: int | None,
    q: str | None = None,
    campos_busca: list[str] | None = None,
    filtros: dict[str, str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ModelT], int]:
    query = _pagina(db, model, filial_id=filial_id)
    for campo, valor in (filtros or {}).items():
        if hasattr(model, campo):
            query = query.filter(getattr(model, campo) == valor)
    termo = (q or "").strip()
    if termo and campos_busca and hasattr(model, "id"):
        ilike = [getattr(model, campo).ilike(f"%{termo}%") for campo in campos_busca]
        query = query.filter(or_(*ilike))
    total = query.count()
    items = query.order_by(model.id.desc()).limit(limit).offset(offset).all()
    return items, total


def buscar_por_id(
    db: Session,
    model: type[ModelT],
    item_id: int,
    *,
    filial_id: int | None = None,
) -> ModelT:
    query = db.query(model).filter(model.id == item_id)
    if filial_id is not None and hasattr(model, "filial_id"):
        query = query.filter(model.filial_id == filial_id)
    item = query.first()
    if not item or (hasattr(item, "ativo") and not item.ativo):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Registro não encontrado.",
        )
    return item


def criar(db: Session, model: type[ModelT], dados: dict[str, Any]) -> ModelT:
    item = model(**dados)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dados duplicados: já existe um registro com esses valores.",
        ) from exc
    db.refresh(item)
    return item


def atualizar(
    db: Session,
    model: type[ModelT],
    item_id: int,
    dados: dict[str, Any],
    *,
    filial_id: int | None = None,
) -> ModelT:
    item = buscar_por_id(db, model, item_id, filial_id=filial_id)
    if "filial_id" in dados:
        dados.pop("filial_id")
    for campo, valor in dados.items():
        setattr(item, campo, valor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dados duplicados: já existe um registro com esses valores.",
        ) from exc
    db.refresh(item)
    return item


def desativar(
    db: Session,
    model: type[ModelT],
    item_id: int,
    *,
    filial_id: int | None = None,
) -> None:
    """Soft delete: seta `ativo=false` (auditoria preservada — padrão do schema)."""
    item = buscar_por_id(db, model, item_id, filial_id=filial_id)
    if hasattr(item, "ativo"):
        item.ativo = False
        db.commit()