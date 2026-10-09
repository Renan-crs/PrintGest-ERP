"""Routers de usuários do sistema — gestão restrita a ADMIN (RBAC §5)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import hash_password
from app.deps import DbDep, RANK, require_nivel, UsuarioDep
from app.models.core import Usuario
from app.models.enums import NivelAcesso
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.schemas.usuarios import UsuarioCreate, UsuarioOut, UsuarioUpdate
from app.services.auth_service import revogar_sessoes
from app.services.crud import atualizar, buscar_por_id, criar, desativar
from sqlalchemy import or_


router = APIRouter(
    prefix="/usuarios",
    tags=["usuários"],
    dependencies=[Depends(require_nivel(NivelAcesso.ADMIN))],
)


def _garantir_nao_auto_lockout(
    db: DbDep, usuario_atual: Usuario, item_id: int, body: UsuarioUpdate
) -> None:
    """Impede que um admin desative/rebaixe a si mesmo e lock-out o sistema.

    P13 (RBAC) e P16 (anti-lockout): o usuário autenticado não pode remover o
    próprio acesso — seja desativando, excluindo ou rebaixando o próprio nível.
    """
    if item_id != usuario_atual.id:
        return
    alvo = db.get(Usuario, item_id) or usuario_atual
    dados = body.model_dump(exclude_unset=True)
    if dados.get("ativo") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar o próprio usuário.",
        )
    novo_nivel = dados.get("nivel_acesso")
    if novo_nivel is not None and RANK[novo_nivel] < RANK[alvo.nivel_acesso]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode rebaixar o próprio nível de acesso.",
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
    limite = min(max(limit, 1), 200)
    desloc = max(offset, 0)
    itens = query.order_by(Usuario.id.desc()).limit(limite).offset(desloc).all()
    return ListaResponse(
        data=[UsuarioOut.model_validate(u) for u in itens],
        meta=MetaPaginacao(total=total, limit=limite, offset=desloc),
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
    item_id: int, body: UsuarioUpdate, db: DbDep, usuario: UsuarioDep
) -> ItemResponse[UsuarioOut]:
    _garantir_nao_auto_lockout(db, usuario, item_id, body)
    dados = body.model_dump(exclude_unset=True)
    redefine_senha = "senha" in dados
    if redefine_senha:
        dados["senha_hash"] = hash_password(dados.pop("senha"))
    atualizado = atualizar(db, Usuario, item_id, dados)
    if redefine_senha:
        # P13/P16: o reset de senha por um admin encerra as sessões ativas do alvo.
        revogar_sessoes(db, item_id)
    return ItemResponse(data=UsuarioOut.model_validate(atualizado))


@router.delete("/{item_id}", status_code=204)
def remover(item_id: int, db: DbDep, usuario: UsuarioDep) -> None:
    if item_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode excluir o próprio usuário.",
        )
    desativar(db, Usuario, item_id)