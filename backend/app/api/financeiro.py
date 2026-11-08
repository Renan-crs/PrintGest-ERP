"""Routers do módulo Financeiro — PRD v2.0 §1.3 (roadmap Fase 3), telas_e_fluxos §1.5.

RBAC: caixa (abertura/extrato/fechamento e sangria/suprimento) exige CAIXA;
contas a receber/pagar e plano de contas exigem GERENTE (PRD §5).
"""

from fastapi import APIRouter, Depends, Query

from app.api.crud_factory import criar_router_crud
from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel, require_perfis
from app.models.enums import NivelAcesso, StatusConta
from app.models.financeiro import PlanoContas
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.financeiro import (
    AbrirCaixaIn,
    BaixaIn,
    CaixaOut,
    ContaPagarOut,
    ContaReceberOut,
    FecharCaixaIn,
    MovimentoCaixaIn,
    MovimentoCaixaOut,
    PlanoContaCreate,
    PlanoContaOut,
    PlanoContaUpdate,
)
from app.services import financeiro_service

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


# --------------------------------------------------------------------- caixa
_caixa = [
    Depends(require_perfis(NivelAcesso.CAIXA, NivelAcesso.GERENTE, NivelAcesso.ADMIN))
]
_gerente = [Depends(require_nivel(NivelAcesso.GERENTE))]


# --------------------------------------------------------------------- caixa
@router.get(
    "/caixa/atual",
    response_model=ItemResponse[CaixaOut | None],
    dependencies=_caixa,
)
def caixa_atual(db: DbDep, filial: FilialDep, usuario: UsuarioDep):
    caixa = financeiro_service.caixa_aberto(db, filial_id=filial, usuario_id=usuario.id)
    return ItemResponse(
        data=None if caixa is None else financeiro_service.caixa_out(db, caixa)
    )


@router.post("/caixa/abrir", response_model=ItemResponse[CaixaOut], dependencies=_caixa)
def abrir_caixa(
    payload: AbrirCaixaIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    caixa = financeiro_service.abrir_caixa(
        db, filial_id=filial, usuario_id=usuario.id, dados=payload
    )
    return ItemResponse(data=financeiro_service.caixa_out(db, caixa))


@router.get(
    "/caixa/{caixa_id}/extrato",
    response_model=ListaResponse[MovimentoCaixaOut],
    dependencies=_caixa,
)
def extrato(
    caixa_id: int,
    db: DbDep,
    filial: FilialDep,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    itens, total = financeiro_service.listar_movimentos(
        db, caixa_id=caixa_id, filial_id=filial, limit=limit, offset=offset
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post(
    "/caixa/{caixa_id}/movimento",
    response_model=ItemResponse[MovimentoCaixaOut],
    dependencies=_caixa,
)
def lancar_movimento(
    caixa_id: int, payload: MovimentoCaixaIn, db: DbDep, filial: FilialDep
):
    movimento = financeiro_service.registrar_movimento(
        db, caixa_id=caixa_id, filial_id=filial, dados=payload
    )
    return ItemResponse(data=movimento)


@router.post(
    "/caixa/{caixa_id}/fechar",
    response_model=ItemResponse[CaixaOut],
    dependencies=_caixa,
)
def fechar_caixa(
    caixa_id: int,
    payload: FecharCaixaIn,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
):
    caixa = financeiro_service.fechar_caixa(
        db, caixa_id=caixa_id, filial_id=filial, usuario_id=usuario.id, dados=payload
    )
    return ItemResponse(data=financeiro_service.caixa_out(db, caixa))


# -------------------------------------------------------------------- contas
@router.get(
    "/contas-receber",
    response_model=ListaResponse[ContaReceberOut],
    dependencies=_gerente,
)
def contas_receber(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    status_conta: StatusConta | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    itens, total = financeiro_service.listar_contas_receber(
        db, filial_id=filial, q=q, status_conta=status_conta, limit=limit, offset=offset
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post(
    "/contas-receber/{conta_id}/baixa",
    response_model=ItemResponse[ContaReceberOut],
    dependencies=_gerente,
)
def baixar_receber(
    conta_id: int, payload: BaixaIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=financeiro_service.baixar_conta_receber(
            db,
            conta_id=conta_id,
            filial_id=filial,
            usuario_id=usuario.id,
            dados=payload,
        )
    )


@router.get(
    "/contas-pagar", response_model=ListaResponse[ContaPagarOut], dependencies=_gerente
)
def contas_pagar(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    status_conta: StatusConta | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    itens, total = financeiro_service.listar_contas_pagar(
        db, filial_id=filial, q=q, status_conta=status_conta, limit=limit, offset=offset
    )
    return ListaResponse(
        data=itens, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post(
    "/contas-pagar/{conta_id}/baixa",
    response_model=ItemResponse[ContaPagarOut],
    dependencies=_gerente,
)
def baixar_pagar(
    conta_id: int, payload: BaixaIn, db: DbDep, filial: FilialDep, usuario: UsuarioDep
):
    return ItemResponse(
        data=financeiro_service.baixar_conta_pagar(
            db,
            conta_id=conta_id,
            filial_id=filial,
            usuario_id=usuario.id,
            dados=payload,
        )
    )


# ------------------------------------------------------------- plano de contas
plano_contas = criar_router_crud(
    prefix="/plano-contas",
    model=PlanoContas,
    schema_in=PlanoContaCreate,
    schema_update=PlanoContaUpdate,
    schema_out=PlanoContaOut,
    campos_busca=["codigo", "nome"],
    campos_filtro=["tipo"],
    tags=["financeiro"],
    nivel_acesso=NivelAcesso.GERENTE,
)


def registrar(api: APIRouter) -> None:
    api.include_router(router)
    api.include_router(plano_contas)
