"""Administração de tabelas de preço e regras vigentes (guia V1).

Escrita restrita a GERENTE+ (mesma regra de preço de cadastro). Toda consulta
e gravação é filtrada pela filial do inquilino — não existe tabela global.
Alterar preço nunca edita a regra usada: `suceder` encerra a atual e cria outra
com nova vigência (RF-VR-12).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.cadastros import Produto
from app.models.enums import NivelAcesso
from app.models.precificacao import RegraPreco, TabelaPreco
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.schemas.precificacao import (
    RegraPrecoCreate,
    RegraPrecoOut,
    TabelaPrecoCreate,
    TabelaPrecoOut,
)
from app.services.precificacao_variacao import (
    FaixaInvalidaError,
    FaixaPreco,
    validar_faixas,
)

router = APIRouter(prefix="/precificacao", tags=["precificação"])


def _tabela_no_escopo(db: Session, tabela_id: int, filial_id: int) -> TabelaPreco:
    tabela = (
        db.query(TabelaPreco)
        .filter(TabelaPreco.id == tabela_id, TabelaPreco.filial_id == filial_id)
        .first()
    )
    if tabela is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tabela de preço não encontrada.",
        )
    return tabela


def _regra_no_escopo(
    db: Session, regra_id: int, filial_id: int
) -> tuple[RegraPreco, TabelaPreco]:
    regra = db.query(RegraPreco).filter(RegraPreco.id == regra_id).first()
    if regra is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Regra não encontrada."
        )
    tabela = _tabela_no_escopo(db, regra.tabela_preco_id, filial_id)
    return regra, tabela


def _validar_faixas_da_regra(dados: RegraPrecoCreate) -> None:
    faixas = tuple(FaixaPreco(f.qtd_min, f.qtd_max, f.preco_unitario) for f in dados.faixas)
    try:
        validar_faixas(faixas)
    except FaixaInvalidaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


def _criar_regra(
    db: Session, dados: RegraPrecoCreate, filial_id: int, usuario_id: int
) -> RegraPreco:
    _tabela_no_escopo(db, dados.tabela_preco_id, filial_id)
    produto = (
        db.query(Produto)
        .filter(Produto.id == dados.produto_id, Produto.filial_id == filial_id)
        .first()
    )
    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado."
        )
    _validar_faixas_da_regra(dados)
    regra = RegraPreco(
        uuid=str(uuid.uuid4()),
        tabela_preco_id=dados.tabela_preco_id,
        produto_id=dados.produto_id,
        preco_base=dados.preco_base,
        faixas=[f.model_dump(mode="json") for f in dados.faixas],
        modificadores=[m.model_dump(mode="json") for m in dados.modificadores],
        minimo=dados.minimo,
        modo_faixa=dados.modo_faixa,
        vigencia_inicio=dados.vigencia_inicio or datetime.now(UTC),
        vigencia_fim=dados.vigencia_fim,
        prioridade=dados.prioridade,
        criado_por=usuario_id,
    )
    db.add(regra)
    db.commit()
    db.refresh(regra)
    return regra


@router.get("/tabelas")
def listar_tabelas(
    db: DbDep, filial: FilialDep, limit: int = 50, offset: int = 0
) -> ListaResponse[TabelaPrecoOut]:
    query = db.query(TabelaPreco).filter(TabelaPreco.filial_id == filial)
    total = query.count()
    itens = (
        query.order_by(TabelaPreco.id.desc())
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
        .all()
    )
    return ListaResponse(
        data=[TabelaPrecoOut.model_validate(t) for t in itens],
        meta=MetaPaginacao(
            total=total, limit=min(max(limit, 1), 200), offset=max(offset, 0)
        ),
    )


@router.post(
    "/tabelas",
    status_code=201,
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def criar_tabela(
    body: TabelaPrecoCreate,
    db: DbDep,
    filial: FilialDep,
    _usuario: UsuarioDep,
) -> ItemResponse[TabelaPrecoOut]:
    if body.padrao and body.cliente_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A tabela padrão não pode ter cliente.",
        )
    duplicata = (
        db.query(TabelaPreco)
        .filter(
            TabelaPreco.filial_id == filial,
            TabelaPreco.cliente_id == body.cliente_id,
            TabelaPreco.padrao.is_(body.padrao),
        )
        .first()
    )
    if duplicata is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe tabela com este escopo.",
        )
    tabela = TabelaPreco(
        uuid=str(uuid.uuid4()),
        filial_id=filial,
        cliente_id=body.cliente_id,
        nome=body.nome,
        padrao=body.padrao,
    )
    db.add(tabela)
    db.commit()
    db.refresh(tabela)
    return ItemResponse(data=TabelaPrecoOut.model_validate(tabela))


@router.get("/regras")
def listar_regras(
    db: DbDep,
    filial: FilialDep,
    tabela_preco_id: int | None = None,
    produto_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ListaResponse[RegraPrecoOut]:
    query = (
        db.query(RegraPreco)
        .join(TabelaPreco, RegraPreco.tabela_preco_id == TabelaPreco.id)
        .filter(TabelaPreco.filial_id == filial)
    )
    if tabela_preco_id is not None:
        query = query.filter(RegraPreco.tabela_preco_id == tabela_preco_id)
    if produto_id is not None:
        query = query.filter(RegraPreco.produto_id == produto_id)
    total = query.count()
    limite, desloc = min(max(limit, 1), 200), max(offset, 0)
    itens = query.order_by(RegraPreco.id.desc()).limit(limite).offset(desloc).all()
    return ListaResponse(
        data=[RegraPrecoOut.model_validate(r) for r in itens],
        meta=MetaPaginacao(total=total, limit=limite, offset=desloc),
    )


@router.post(
    "/regras",
    status_code=201,
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def criar_regra(
    body: RegraPrecoCreate,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
) -> ItemResponse[RegraPrecoOut]:
    regra = _criar_regra(db, body, filial, usuario.id)
    return ItemResponse(data=RegraPrecoOut.model_validate(regra))


@router.post(
    "/regras/{regra_id}/encerrar",
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def encerrar_regra(
    regra_id: int, db: DbDep, filial: FilialDep, _usuario: UsuarioDep
) -> ItemResponse[RegraPrecoOut]:
    regra, _ = _regra_no_escopo(db, regra_id, filial)
    if regra.vigencia_fim is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta regra já está encerrada.",
        )
    regra.vigencia_fim = datetime.now(UTC)
    db.commit()
    db.refresh(regra)
    return ItemResponse(data=RegraPrecoOut.model_validate(regra))


@router.post(
    "/regras/{regra_id}/suceder",
    status_code=201,
    dependencies=[Depends(require_nivel(NivelAcesso.GERENTE))],
)
def suceder_regra(
    regra_id: int,
    body: RegraPrecoCreate,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
) -> ItemResponse[RegraPrecoOut]:
    """Encerra a regra atual e cria a sucessora com nova vigência (RF-VR-12)."""
    regra, tabela = _regra_no_escopo(db, regra_id, filial)
    if body.tabela_preco_id != tabela.id or body.produto_id != regra.produto_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A sucessora deve manter a mesma tabela e o mesmo produto.",
        )
    if regra.vigencia_fim is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta regra já está encerrada.",
        )
    agora = datetime.now(UTC)
    regra.vigencia_fim = agora
    nova = _criar_regra(
        db,
        body.model_copy(update={"vigencia_inicio": body.vigencia_inicio or agora}),
        filial,
        usuario.id,
    )
    return ItemResponse(data=RegraPrecoOut.model_validate(nova))


def registrar(api: APIRouter) -> None:
    # Escrita: GERENTE+. Leitura: OPERADOR+.
    api.include_router(
        router,
        dependencies=[Depends(require_nivel(NivelAcesso.OPERADOR))],
    )
