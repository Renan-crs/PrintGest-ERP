"""Routers da Venda de Balcão (PDV) — PRD v2.0 §2.2 fluxo Balcão, roadmap item 7.

Nível mínimo de acesso: CAIXA — diferente da OS (OPERADOR). O caixa "tem venda
de balcão e movimentação de caixa apenas" (PRD §5 RBAC), logo PODE registrar e
cancelar vendas de balcão; o cancelamento estorna o estoque automaticamente.
"""

from fastapi import APIRouter, Depends, Query, status

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import (
    FormaPagamento,
    NivelAcesso,
    StatusVenda,
)
from app.models.movimento import VendaBalcao
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.venda import VendaCreate, VendaOut
from app.services import venda_service

router = APIRouter(
    prefix="/vendas",
    tags=["movimento"],
    dependencies=[Depends(require_nivel(NivelAcesso.CAIXA))],
)


def _para_out(venda: VendaBalcao) -> VendaOut:
    return venda_service._para_out(venda)


@router.get("")
def listar(
    db: DbDep,
    filial: FilialDep,
    status_venda: StatusVenda | None = None,
    forma_pagamento: FormaPagamento | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse[VendaOut]:
    itens, total = venda_service.listar(
        db,
        filial_id=filial.id,
        status_venda=status_venda,
        forma_pagamento=forma_pagamento,
        q=q,
        limit=limit,
        offset=offset,
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post("")
def criar(
    payload: VendaCreate,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
) -> ItemResponse[VendaOut]:
    return ItemResponse(data=venda_service.criar(
        db, filial_id=filial.id, usuario_id=usuario.id, dados=payload
    ))


@router.get("/{venda_id}")
def buscar(venda_id: int, db: DbDep, filial: FilialDep) -> ItemResponse[VendaOut]:
    return ItemResponse(data=_para_out(venda_service.buscar(
        db, filial_id=filial.id, venda_id=venda_id
    )))


@router.delete("/{venda_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(venda_id: int, db: DbDep, filial: FilialDep) -> None:
    venda_service.cancelar(db, filial_id=filial.id, venda_id=venda_id)
