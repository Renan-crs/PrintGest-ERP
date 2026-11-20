"""Routers do módulo Fiscal — PRD v2.1 §1.3 / telas_e_fluxos §1.6.

Consulta, emissão via gateway de terceiro, consulta de status, cancelamento e
trilha de auditoria. RBAC: caixa/gerente/admin (menu v2.1). Todas as rotas são
escopadas à filial do usuário autenticado.
"""

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep, FilialDep, UsuarioDep, require_perfis
from app.models.enums import ModeloFiscal, NivelAcesso, StatusFiscal
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.fiscal import (
    DocumentoFiscalOut,
    FiscalCancelarIn,
    FiscalEmitirIn,
    FiscalEventoOut,
    ResumoFiscal,
)
from app.services import fiscal_service

router = APIRouter(
    prefix="/fiscal",
    tags=["fiscal"],
    dependencies=[
        Depends(
            require_perfis(NivelAcesso.CAIXA, NivelAcesso.GERENTE, NivelAcesso.ADMIN)
        )
    ],
)


@router.get("/documentos", response_model=ListaResponse[DocumentoFiscalOut])
def documentos(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    modelo: ModeloFiscal | None = None,
    status_fiscal: StatusFiscal | None = None,
    contingencia: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    itens, total = fiscal_service.listar_documentos(
        db,
        filial_id=filial,
        q=q,
        modelo=modelo,
        status_fiscal=status_fiscal,
        contingencia=contingencia,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.get("/resumo", response_model=ItemResponse[ResumoFiscal])
def resumo(db: DbDep, filial: FilialDep):
    return ItemResponse(data=fiscal_service.resumo(db, filial_id=filial))


@router.get("/gateway", response_model=ItemResponse[dict])
def gateway(db: DbDep, filial: FilialDep):
    """Estado do gateway da filial, sem expor token/credenciais."""
    return ItemResponse(data=fiscal_service.gateway_info(db, filial))


@router.post("/documentos/emitir", response_model=ItemResponse[DocumentoFiscalOut])
def emitir(payload: FiscalEmitirIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    return ItemResponse(
        data=fiscal_service.emitir(
            db,
            filial_id=filial,
            usuario_id=usuario.id,
            modelo=payload.modelo,
            venda_balcao_id=payload.venda_balcao_id,
            ordem_servico_id=payload.ordem_servico_id,
            contingencia=payload.contingencia,
        )
    )


@router.get("/documentos/{item_id}", response_model=ItemResponse[DocumentoFiscalOut])
def documento(item_id: int, db: DbDep, filial: FilialDep):
    return ItemResponse(
        data=fiscal_service.obter_documento(db, item_id=item_id, filial_id=filial)
    )


@router.get(
    "/documentos/{item_id}/eventos", response_model=ListaResponse[FiscalEventoOut]
)
def eventos(item_id: int, db: DbDep, filial: FilialDep):
    linhas = fiscal_service.listar_eventos(db, documento_id=item_id, filial_id=filial)
    return ListaResponse(
        data=linhas,
        meta=MetaPaginacao(total=len(linhas), limit=len(linhas) or 1, offset=0),
    )


@router.post(
    "/documentos/{item_id}/consultar", response_model=ItemResponse[DocumentoFiscalOut]
)
def consultar(item_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    return ItemResponse(
        data=fiscal_service.consultar(
            db, item_id=item_id, filial_id=filial, usuario_id=usuario.id
        )
    )


@router.post(
    "/documentos/{item_id}/cancelar", response_model=ItemResponse[DocumentoFiscalOut]
)
def cancelar(
    item_id: int,
    payload: FiscalCancelarIn,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
):
    return ItemResponse(
        data=fiscal_service.cancelar(
            db,
            item_id=item_id,
            filial_id=filial,
            usuario_id=usuario.id,
            motivo=payload.motivo,
        )
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)
