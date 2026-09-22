"""Routers de usuários do sistema — gestão restrita a ADMIN (RBAC §5)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import hash_password
from app.deps import DbDep, require_nivel
from app.models.core import Usuario
from app.models.enums import NivelAcesso
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.schemas.usuarios import UsuarioCreate, UsuarioOut, UsuarioUpdate
from app.services.crud import atualizar, buscar_por_id, criar, desativar
from sqlalchemy import or_


router = APIRouter(
    prefix="/usuarios",
    tags=["usuários"],
    dependencies=[Depends(require_nivel(NivelAcesso.ADMIN))],
)


@router.get("")
def lista(
    db: DbDep,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ListaResponse[UsuarioOut]:
    query = db.query(Usuario)
    termo = (q or "").strip()
    if termo:
        query = query.filter(
            or_(
                Usuario.nome.ilike(f"%{termo}%"),
                Usuario.login.ilike(f"%{termo}%"),
                Usuario.email.ilike(f"%{termo}%"),
            )
        )
    total = query.count()
    itens = query.order_by(Usuario.id.desc()).limit(min(max(limit, 1), 200)).offset(max(offset, 0)).all()
    return ListaResponse(
        data=[UsuarioOut.model_validate(u) for u in itens],
        meta=MetaPaginacao(total=total, limit=limit, offset=offset),
    )


@router.get("/{item_id}")
def detalhe(item_id: int, db: DbDep) -> ItemResponse[UsuarioOut]:
    return ItemResponse(data=UsuarioOut.model_validate(buscar_por_id(db, Usuario, item_id)))


@router.post("")
def criar_usuario(body: UsuarioCreate, db: DbDep) -> ItemResponse[UsuarioOut]:
    dados = body.model_dump()
    senha = dados.pop("senha")
    dados["senha_hash"] = hash_password(senha)
    return ItemResponse(data=UsuarioOut.model_validate(criar(db, Usuario, dados)))


@router.put("/{item_id}")
def atualizar_usuario(
    item_id: int, body: UsuarioUpdate, db: DbDep
) -> ItemResponse[UsuarioOut]:
    dados = body.model_dump(exclude_unset=True)
    if "senha" in dados:
        dados["senha_hash"] = hash_password(dados.pop("senha"))
    return ItemResponse(data=UsuarioOut.model_validate(atualizar(db, Usuario, item_id, dados)))


@router.delete("/{item_id}", status_code=204)
def remover(item_id: int, db: DbDep) -> None:
    desativar(db, Usuario, item_id)