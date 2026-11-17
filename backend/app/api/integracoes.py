"""Rotas de integrações com aplicações de terceiros (PRD v3.3 §3.6).

Admin-only (o segredo nunca é lido/alterado por outro perfil). Escritas passam
pelo middleware de modo leitura (423) e pelo gating de `configuracoes` (403).
"""

from fastapi import APIRouter, Depends

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import NivelAcesso
from app.schemas.common import ItemResponse
from app.schemas.integracao import (
    IntegracaoCreate,
    IntegracaoEventoOut,
    IntegracaoOut,
    IntegracaoTesteOut,
    IntegracaoUpdate,
    ListaIntegracoes,
)
from app.services import integracao_service

router = APIRouter(
    prefix="/config/integracoes",
    tags=["configuracao", "integracoes"],
    dependencies=[Depends(require_nivel(NivelAcesso.ADMIN))],
)


@router.get("", response_model=ListaIntegracoes)
def listar(db: DbDep, filial: FilialDep):
    return integracao_service.listar(db, filial_id=filial)


@router.post("", response_model=ItemResponse[IntegracaoOut], status_code=201)
def criar(payload: IntegracaoCreate, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    return ItemResponse(
        data=integracao_service.criar(
            db,
            filial_id=filial,
            usuario_id=usuario.id,
            dados=payload.model_dump(exclude_unset=True),
        )
    )


@router.get("/{item_id}", response_model=ItemResponse[IntegracaoOut])
def obter(item_id: int, db: DbDep, filial: FilialDep):
    return ItemResponse(
        data=integracao_service._para_out(
            integracao_service.obter(db, item_id=item_id, filial_id=filial)
        )
    )


@router.post("/{item_id}/testar", response_model=ItemResponse[IntegracaoTesteOut])
def testar(
    item_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=integracao_service.testar(
            db, item_id=item_id, filial_id=filial, usuario_id=usuario.id
        )
    )


@router.get("/{item_id}/eventos", response_model=list[IntegracaoEventoOut])
def eventos(item_id: int, db: DbDep, filial: FilialDep):
    return integracao_service.eventos(db, item_id=item_id, filial_id=filial)


@router.put("/{item_id}", response_model=ItemResponse[IntegracaoOut])
def atualizar(
    item_id: int,
    payload: IntegracaoUpdate,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
):
    return ItemResponse(
        data=integracao_service.atualizar(
            db,
            item_id=item_id,
            filial_id=filial,
            usuario_id=usuario.id,
            dados=payload.model_dump(exclude_unset=True),
        )
    )


@router.delete("/{item_id}", status_code=204)
def excluir(item_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep) -> None:
    integracao_service.excluir(
        db, item_id=item_id, filial_id=filial, usuario_id=usuario.id
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)
