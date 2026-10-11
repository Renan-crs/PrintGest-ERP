"""Routers do módulo Fiscal — PRD v2.1 §1.3 / telas_e_fluxos §1.6 (somente leitura).

A emissão de NF-e/NFC-e depende de um gateway fiscal externo que não existe
neste produto; estas rotas entregam a **consulta** dos documentos e o **resumo**
usado pela tela de contingência. RBAC: caixa/gerente/admin (menu v2.1).
"""

from fastapi import APIRouter, Depends, Query

from app.deps import DbDep, FilialDep, require_perfis
from app.models.enums import ModeloFiscal, NivelAcesso, StatusFiscal
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.fiscal import DocumentoFiscalOut, ResumoFiscal
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


@router.get("/documentos/{item_id}", response_model=ItemResponse[DocumentoFiscalOut])
def documento(item_id: int, db: DbDep, filial: FilialDep):
    return ItemResponse(
        data=fiscal_service.obter_documento(db, item_id=item_id, filial_id=filial)
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)
