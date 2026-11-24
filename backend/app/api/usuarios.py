"""Routers de usuários do sistema — gestão restrita a ADMIN (RBAC §5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import or_

from app.core.security import hash_password
from app.deps import RANK, DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.core import Usuario
from app.models.enums import NivelAcesso
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.schemas.usuarios import UsuarioCreate, UsuarioOut, UsuarioUpdate
from app.services import tenants
from app.services.auth_service import revogar_sessoes
from app.services.crud import atualizar, criar, desativar

router = APIRouter(
    prefix="/usuarios",
    tags=["usuários"],
    dependencies=[Depends(require_nivel(NivelAcesso.ADMIN))],
)


def _escopo(db: DbDep):
    """Usuários do INQUILINO desta instalação (legado: todos)."""
    consulta = db.query(Usuario)
    filiais = tenants.filiais_do_tenant(db)
    if filiais:
        consulta = consulta.filter(Usuario.filial_id.in_(filiais))
    return consulta


def _buscar_no_escopo(db: DbDep, item_id: int) -> Usuario:
    """Busca por id dentro do inquilino; 404 se não pertencer a ele."""
    usuario = _escopo(db).filter(Usuario.id == item_id).first()
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado.",
        )
    return usuario


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
    query = _escopo(db)
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
    return ItemResponse(data=UsuarioOut.model_validate(_buscar_no_escopo(db, item_id)))


@router.post("")
def criar_usuario(
    body: UsuarioCreate, db: DbDep, filial: FilialDep
) -> ItemResponse[UsuarioOut]:
    dados = body.model_dump()
    senha = dados.pop("senha")
    dados["senha_hash"] = hash_password(senha)
    # Multi-tenant: o usuário nasce NA filial do inquilino — o corpo do
    # request não escolhe filial (mesma regra da factory de cadastros).
    dados["filial_id"] = filial
    return ItemResponse(data=UsuarioOut.model_validate(criar(db, Usuario, dados)))


@router.put("/{item_id}")
def atualizar_usuario(
    item_id: int,
    body: UsuarioUpdate,
    db: DbDep,
    usuario: UsuarioDep,
    authorization: Annotated[str | None, Header()] = None,
) -> ItemResponse[UsuarioOut]:
    _garantir_nao_auto_lockout(db, usuario, item_id, body)
    _buscar_no_escopo(db, item_id)  # 404 se fora do inquilino
    dados = body.model_dump(exclude_unset=True)
    # Trocar de filial moveria o usuário para outro inquilino — proibido.
    dados.pop("filial_id", None)
    redefine_senha = "senha" in dados
    if redefine_senha:
        dados["senha_hash"] = hash_password(dados.pop("senha"))
        # A4: redefinir a senha também resolve o estado de acesso — limpa as
        # tentativas falhas, o bloqueio temporário e a exigência de primeiro
        # acesso (senão o usuário continuaria 423/407 após a nova senha).
        dados["falhas_login"] = 0
        dados["bloqueado_em"] = None
        dados["primeiro_acesso"] = False
    atualizado = atualizar(db, Usuario, item_id, dados)
    if redefine_senha:
        # P13/P16: encerra as demais sessões do alvo, preservando a que executou
        # a operação (um admin resetando a própria senha não perde o acesso).
        token_atual = (authorization or "").removeprefix("Bearer ").strip() or None
        revogar_sessoes(db, item_id, preservar_token=token_atual)
    return ItemResponse(data=UsuarioOut.model_validate(atualizado))


@router.post("/{item_id}/desbloquear")
def desbloquear_usuario(
    item_id: int, db: DbDep, usuario: UsuarioDep
) -> ItemResponse[UsuarioOut]:
    """A11: desbloqueia um usuário após excesso de tentativas falhas.

    Limpa apenas o estado de lockout (`falhas_login`/`bloqueado_em`); senha e
    primeiro acesso permanecem intactos. Restrito a ADMIN pelo router.
    """
    alvo = _buscar_no_escopo(db, item_id)  # 404 se fora do inquilino
    alvo.falhas_login = 0
    alvo.bloqueado_em = None
    db.commit()
    db.refresh(alvo)
    return ItemResponse(data=UsuarioOut.model_validate(alvo))


@router.delete("/{item_id}", status_code=204)
def remover(item_id: int, db: DbDep, usuario: UsuarioDep) -> None:
    if item_id == usuario.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode excluir o próprio usuário.",
        )
    _buscar_no_escopo(db, item_id)  # 404 se fora do inquilino
    desativar(db, Usuario, item_id)
