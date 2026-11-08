"""Routers da Venda de Balcão (PDV) — PRD v2.0 §2.2 fluxo Balcão, roadmap item 7.

Nível mínimo de acesso: CAIXA — diferente da OS (OPERADOR). O caixa "tem venda
de balcão e movimentação de caixa apenas" (PRD §5 RBAC), logo PODE registrar e
cancelar vendas de balcão; o cancelamento estorna o estoque automaticamente.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import (
    FormaPagamento,
    NivelAcesso,
    StatusVenda,
)
from app.models.movimento import VendaBalcao
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.venda import VendaCreate, VendaOut
from app.services import financeiro_service, venda_service

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
        filial_id=filial,
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
    # M0 (PRD v3.0 §2): o PDV não opera com caixa fechado — o vendedor logado
    # precisa do próprio caixa aberto antes de registrar vendas.
    if (
        financeiro_service.caixa_aberto(db, filial_id=filial, usuario_id=usuario.id)
        is None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Caixa fechado — abra o caixa antes de registrar vendas.",
        )
    return ItemResponse(
        data=venda_service.criar(
            db, filial_id=filial, usuario_id=usuario.id, dados=payload
        )
    )


@router.get("/{venda_id}")
def buscar(venda_id: int, db: DbDep, filial: FilialDep) -> ItemResponse[VendaOut]:
    return ItemResponse(
        data=_para_out(venda_service.buscar(db, filial_id=filial, venda_id=venda_id))
    )


@router.delete("/{venda_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(venda_id: int, db: DbDep, filial: FilialDep) -> None:
    venda_service.cancelar(db, filial_id=filial, venda_id=venda_id)
