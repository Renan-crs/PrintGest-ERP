"""Routers de movimento — Ordem de Serviço e Orçamento (Fase 2).

Cobre: lista (com filtro por status), formulário, atualização, cancelamento,
transições de status (fluxo PRD v2.0 §2.1) e conversão de orçamento em OS.

Nível mínimo de acesso: OPERADOR ("cadastros e movimento" — RBAC §5).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import joinedload, selectinload

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.cadastros import Cliente
from app.models.enums import NivelAcesso, StatusOs, TipoOs
from app.models.movimento import OrdemServico, OrdemServicoItem
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.schemas.movimento import (
    CotacaoIn,
    CotacaoOut,
    OsConverterIn,
    OsCreate,
    OsOut,
    OsStatusIn,
    OsUpdate,
)
from app.services import cotacao_service, os_service

router = APIRouter(
    prefix="/os",
    tags=["movimento"],
    dependencies=[Depends(require_nivel(NivelAcesso.OPERADOR))],
)


def _opções_carga():
    return (
        joinedload(OrdemServico.cliente),
        joinedload(OrdemServico.vendedor),
        joinedload(OrdemServico.atendente),
        selectinload(OrdemServico.itens),
    selectinload(OrdemServico.itens).selectinload(OrdemServicoItem.cotacoes),
    )


@router.get("")
def listar(
    db: DbDep,
    filial: FilialDep,
    status: StatusOs | None = None,
    tipo: TipoOs | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ListaResponse[OsOut]:
    limite = min(max(limit, 1), 200)
    desloc = max(offset, 0)
    base = db.query(OrdemServico).filter(OrdemServico.filial_id == filial)
    if status:
        base = base.filter(OrdemServico.status == status)
    if tipo:
        base = base.filter(OrdemServico.tipo == tipo)
    termo = (q or "").strip()
    if termo:
        base = base.outerjoin(Cliente, OrdemServico.cliente_id == Cliente.id).filter(
            or_(
                Cliente.nome_razao.ilike(f"%{termo}%"),
                cast(OrdemServico.numero, String).ilike(f"%{termo}%"),
            )
        )
    total = base.count()
    itens = (
        base.order_by(OrdemServico.numero.desc())
        .limit(limite)
        .offset(desloc)
        .options(*_opções_carga())
        .all()
    )
    return ListaResponse(
        data=[os_service._para_out(o) for o in itens],
        meta=MetaPaginacao(total=total, limit=limite, offset=desloc),
    )


@router.get("/{os_id}")
def detalhe(os_id: int, db: DbDep, filial: FilialDep) -> ItemResponse[OsOut]:
    return ItemResponse(data=os_service._para_out(os_service.buscar(db, os_id, filial_id=filial)))


@router.post("")
def criar(
    body: OsCreate, db: DbDep, filial: FilialDep, usuario: UsuarioDep
) -> ItemResponse[OsOut]:
    return ItemResponse(
        data=os_service.criar(db, filial_id=filial, usuario_id=usuario.id, dados=body)
    )


@router.put("/{os_id}")
def atualizar(
    os_id: int, body: OsUpdate, db: DbDep, filial: FilialDep
) -> ItemResponse[OsOut]:
    return ItemResponse(
        data=os_service.atualizar(db, filial_id=filial, os_id=os_id, dados=body)
    )


@router.delete("/{os_id}", status_code=204)
def cancelar(os_id: int, db: DbDep, filial: FilialDep) -> None:
    os_service.cancelar(db, filial_id=filial, os_id=os_id)


@router.post("/{os_id}/converter")
def converter(
    os_id: int,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
    body: OsConverterIn | None = None,
) -> ItemResponse[OsOut]:
    confirmado = body.pagamento_confirmado if body else False
    return ItemResponse(
        data=os_service.converter_em_os(
            db,
            filial_id=filial,
            orcamento_id=os_id,
            usuario_id=usuario.id,
            pagamento_confirmado=confirmado,
        )
    )


@router.patch("/{os_id}/status")
def alterar_status(
    os_id: int, body: OsStatusIn, db: DbDep, filial: FilialDep
) -> ItemResponse[OsOut]:
    return ItemResponse(
        data=os_service.mudar_status(db, filial_id=filial, os_id=os_id, novo=body.status)
    )


# ------------------------------------------- cotações de itens de fornecedor (M1)
# `lancar_cotacao`/`ajustar` = Admin/Gerente (§3.2.3); o comparativo é de quem
# vê a OS (Operador), com os campos sensíveis OMITIDOS no serviço.


@router.get(
    "/{os_id}/itens/{item_id}/cotacoes",
)
def listar_cotacoes(
    os_id: int, item_id: int, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return cotacao_service.listar(db, item_id=item_id, filial_id=filial, usuario=usuario)


@router.post(
    "/{os_id}/itens/{item_id}/cotacoes",
    status_code=201,
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def lancar_cotacao(
    os_id: int,
    item_id: int,
    body: CotacaoIn,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
):
    return ItemResponse(
        data=cotacao_service.lancar(
            db, item_id=item_id, filial_id=filial, usuario=usuario, dados=body
        )
    )


@router.put(
    "/{os_id}/itens/{item_id}/cotacoes/{cotacao_id}/selecionar",
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def selecionar_cotacao(
    os_id: int,
    item_id: int,
    cotacao_id: int,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
):
    return ItemResponse(
        data=cotacao_service.selecionar(
            db, item_id=item_id, cotacao_id=cotacao_id, filial_id=filial, usuario=usuario
        )
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)