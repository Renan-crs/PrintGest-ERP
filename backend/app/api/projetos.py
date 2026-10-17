"""Routers do módulo Projetos (PRD Módulo Projetos — Quadro Kanban).

Namespace **novo** (`/v1/projetos`), aditivo: `/v1/os` e o quadro atual seguem
intactos; a troca de fonte da tela acontece quando a UI nova estiver pronta.

RBAC: o quadro é de operação (Admin, Gerente e Operador — PRD §1.5; Caixa sem
acesso). A **estrutura** do quadro (criar/renomear/reordenar/arquivar/excluir
listas) é de Admin e Gerente; a **exclusão definitiva** é só de Admin (RN6).
A visibilidade de cartões (PV1–PV5) é aplicada no servidor, no service.
"""

from fastapi import APIRouter, Depends, Query


from app.deps import DbDep, FilialDep, UsuarioDep, require_perfis
from app.models.enums import NivelAcesso
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.projetos import (
    AtribuirCartaoIn,
    CartaoCreate,
    CartaoOut,
    CartaoUpdate,
    ListaCreate,
    ListaOut,
    ListaUpdate,
    MembroIn,
    MoverCartaoIn,
    QuadroOut,
    VersaoIn,
)
from app.services import projetos_service as svc

router = APIRouter(
    prefix="/projetos",
    tags=["projetos"],
    dependencies=[
        Depends(require_perfis(NivelAcesso.ADMIN, NivelAcesso.GERENTE, NivelAcesso.OPERADOR))
    ],
)

# Gestores administram a estrutura do quadro (§4.1: criar/renomear/listas).
_somente_gestor = Depends(
    require_perfis(NivelAcesso.ADMIN, NivelAcesso.GERENTE)
)
_somente_admin = Depends(require_perfis(NivelAcesso.ADMIN))


# --------------------------------------------------------------------- quadro


@router.get("/quadro", response_model=ItemResponse[QuadroOut])
def obter_quadro(db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    quadro = svc.obter_quadro(db, filial)
    return ItemResponse(data=svc.quadro_out(db, usuario, quadro))


@router.post(
    "/quadro/listas",
    response_model=ItemResponse[ListaOut],
    status_code=201,
    dependencies=[_somente_gestor],
)
def criar_lista(body: ListaCreate, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    quadro = svc.obter_quadro(db, filial)
    return ItemResponse(
        data=svc.criar_lista(db, usuario=usuario, quadro=quadro, dados=body.model_dump())
    )


@router.patch(
    "/quadro/listas/{lista_id}",
    response_model=ItemResponse[ListaOut],
    dependencies=[_somente_gestor],
)
def atualizar_lista(
    lista_id: int, body: ListaUpdate, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    quadro = svc.obter_quadro(db, filial)
    return ItemResponse(
        data=svc.atualizar_lista(
            db,
            usuario=usuario,
            quadro=quadro,
            lista_id=lista_id,
            dados=body.model_dump(exclude_unset=True),
        )
    )


@router.patch(
    "/quadro/listas/{lista_id}/arquivar",
    response_model=ItemResponse[ListaOut],
    dependencies=[_somente_gestor],
)
def arquivar_lista(lista_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    quadro = svc.obter_quadro(db, filial)
    return ItemResponse(
        data=svc.arquivar_lista(db, usuario=usuario, quadro=quadro, lista_id=lista_id)
    )


@router.delete(
    "/quadro/listas/{lista_id}",
    status_code=204,
    dependencies=[_somente_admin],
)
def excluir_lista(lista_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    quadro = svc.obter_quadro(db, filial)
    svc.excluir_lista(db, usuario=usuario, quadro=quadro, lista_id=lista_id)


# -------------------------------------------------------------------- cartões


@router.get("/cartoes", response_model=ListaResponse[CartaoOut])
def listar_cartoes(
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
    q: str | None = None,
    lista_id: int | None = None,
    arquivado: bool = False,
    sou_membro: bool | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    itens, total = svc.listar_cartoes(
        db,
        usuario=usuario,
        filial_id=filial,
        q=q,
        lista_id=lista_id,
        arquivado=arquivado,
        sou_membro=sou_membro,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post("/cartoes", response_model=ItemResponse[CartaoOut], status_code=201)
def criar_cartao(body: CartaoCreate, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    return ItemResponse(
        data=svc.criar_cartao(db, usuario=usuario, filial_id=filial, dados=body.model_dump())
    )


@router.get("/cartoes/{cartao_id}", response_model=ItemResponse[CartaoOut])
def obter_cartao(cartao_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    return ItemResponse(
        data=svc.obter_cartao(db, usuario=usuario, filial_id=filial, cartao_id=cartao_id)
    )


@router.patch("/cartoes/{cartao_id}", response_model=ItemResponse[CartaoOut])
def atualizar_cartao(
    cartao_id: int, body: CartaoUpdate, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.atualizar_cartao(
            db,
            usuario=usuario,
            filial_id=filial,
            cartao_id=cartao_id,
            dados=body.model_dump(exclude_unset=True),
        )
    )


@router.patch("/cartoes/{cartao_id}/mover", response_model=ItemResponse[CartaoOut])
def mover_cartao(
    cartao_id: int, body: MoverCartaoIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.mover_cartao(
            db,
            usuario=usuario,
            filial_id=filial,
            cartao_id=cartao_id,
            lista_id=body.lista_id,
            indice=body.posicao,
            versao=body.versao,
        )
    )


@router.patch("/cartoes/{cartao_id}/arquivar", response_model=ItemResponse[CartaoOut])
def arquivar_cartao(
    cartao_id: int, body: VersaoIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.arquivar_cartao(
            db, usuario=usuario, filial_id=filial, cartao_id=cartao_id, versao=body.versao
        )
    )


@router.patch("/cartoes/{cartao_id}/restaurar", response_model=ItemResponse[CartaoOut])
def restaurar_cartao(
    cartao_id: int, body: VersaoIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.restaurar_cartao(
            db, usuario=usuario, filial_id=filial, cartao_id=cartao_id, versao=body.versao
        )
    )


@router.patch("/cartoes/{cartao_id}/atribuir", response_model=ItemResponse[CartaoOut])
def atribuir_cartao(
    cartao_id: int, body: AtribuirCartaoIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.atribuir_cartao(
            db,
            usuario=usuario,
            filial_id=filial,
            cartao_id=cartao_id,
            usuario_id=body.usuario_id,
            versao=body.versao,
        )
    )


@router.post("/cartoes/{cartao_id}/membros", response_model=ItemResponse[CartaoOut])
def adicionar_membro(
    cartao_id: int, body: MembroIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.adicionar_membro(
            db,
            usuario=usuario,
            filial_id=filial,
            cartao_id=cartao_id,
            membro_id=body.usuario_id,
        )
    )


@router.delete(
    "/cartoes/{cartao_id}/membros/{membro_id}", response_model=ItemResponse[CartaoOut]
)
def remover_membro(
    cartao_id: int, membro_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=svc.remover_membro(
            db,
            usuario=usuario,
            filial_id=filial,
            cartao_id=cartao_id,
            membro_id=membro_id,
        )
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)
