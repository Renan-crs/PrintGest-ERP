"""Serviços do módulo Estoque — consulta de saldos, kardex, movimentação manual e reposição.

Regras centrais (mockups 4.1–4.3):
  - A movimentação manual grava `movimento_estoque` com origem `ajuste_manual` e,
    na MESMA transação, atualiza `produto_estoque.saldo` (com `FOR UPDATE`).
  - ENTRADA soma; SAIDA subtrai (409 se saldo insuficiente); AJUSTE iguala o
    saldo ao valor informado (é o novo saldo físico da contagem).
  - `quantidade` do kardex tem sinal: entrada +, saída −, ajuste o delta.
  - Reposição (mockup 4.3): itens com saldo < mínimo; giro diário = consumo dos
    últimos 30 dias / 30; autonomia = saldo / giro; sugestão de lote =
    max(mínimo, giro × lead-time) − saldo.
"""

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.cadastros import (
    MovimentoEstoque,
    Produto,
    ProdutoCategoria,
    ProdutoEstoque,
)
from app.models.core import Usuario
from app.models.enums import OrigemMov, TipoMovEstoque, TipoProduto
from app.schemas.estoque import (
    EstoqueLinhaOut,
    EstoqueResumoOut,
    KardexOut,
    MovimentarIn,
    ReposicaoOut,
)

_DIAS_JANELA = 30
_LEAD_DIAS = Decimal("3.2")


def _q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _money(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _status(saldo: Decimal, minimo: Decimal) -> str:
    if saldo < minimo:
        return "critico"
    if minimo > 0 and saldo < minimo * Decimal("1.5"):
        return "atencao"
    return "normal"


def _buscar_produto(db: Session, filial_id: int, produto_id: int) -> Produto:
    produto = (
        db.query(Produto)
        .filter(Produto.id == produto_id, Produto.filial_id == filial_id)
        .first()
    )
    if produto is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Produto não encontrado nesta filial.",
        )
    if produto.tipo != TipoProduto.PRODUTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Serviços não possuem estoque.",
        )
    if not produto.controla_estoque:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produto não controla estoque.",
        )
    return produto


def _rows_produtos(
    db: Session,
    filial_id: int,
    *,
    q: str | None = None,
    categoria_id: int | None = None,
    abaixo_minimo: bool = False,
) -> Any:
    """Linhas (Produto + categoria + saldo/reservado) dos insumos da filial."""
    filtros = [
        Produto.filial_id == filial_id,
        Produto.tipo == TipoProduto.PRODUTO,
        Produto.controla_estoque.is_(True),
    ]
    if q:
        termo = f"%{q.strip()}%"
        filtros.append(
            or_(Produto.codigo.ilike(termo), Produto.nome.ilike(termo))
        )
    if categoria_id is not None:
        filtros.append(Produto.categoria_id == categoria_id)

    saldo_expr = func.coalesce(ProdutoEstoque.saldo, 0).label("saldo")
    reservado_expr = func.coalesce(ProdutoEstoque.reservado, 0).label("reservado")

    qry = (
        db.query(
            Produto.id.label("produto_id"),
            Produto.codigo,
            Produto.nome,
            Produto.categoria_id,
            Produto.unidade,
            Produto.dimensoes,
            Produto.preco_custo,
            Produto.preco_venda,
            Produto.estoque_minimo,
            Produto.ativo,
            ProdutoCategoria.nome.label("categoria_nome"),
            saldo_expr,
            reservado_expr,
        )
        .outerjoin(
            ProdutoEstoque,
            and_(
                ProdutoEstoque.produto_id == Produto.id,
                ProdutoEstoque.filial_id == filial_id,
            ),
        )
        .outerjoin(ProdutoCategoria, ProdutoCategoria.id == Produto.categoria_id)
        .filter(*filtros)
    )
    if abaixo_minimo:
        qry = qry.filter(saldo_expr < Produto.estoque_minimo)
    return qry


def _linha_out(r: Any) -> EstoqueLinhaOut:
    saldo = _q(Decimal(r.saldo))
    reservado = _q(Decimal(r.reservado))
    custo = _money(Decimal(r.preco_custo))
    minimo = _q(Decimal(r.estoque_minimo))
    return EstoqueLinhaOut(
        produto_id=r.produto_id,
        codigo=r.codigo,
        nome=r.nome,
        categoria_id=r.categoria_id,
        categoria_nome=r.categoria_nome,
        unidade=r.unidade,
        dimensoes=r.dimensoes,
        e_bobina=bool(r.dimensoes),
        preco_custo=custo,
        preco_venda=_money(Decimal(r.preco_venda)),
        estoque_minimo=minimo,
        saldo=saldo,
        reservado=reservado,
        disponivel=_q(saldo - reservado),
        valor_estoque=_money(saldo * custo),
        status=_status(saldo, minimo),
        ativo=bool(r.ativo),
    )


def consultar(
    db: Session,
    filial_id: int,
    *,
    q: str | None = None,
    categoria_id: int | None = None,
    abaixo_minimo: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[EstoqueLinhaOut], int]:
    qry = _rows_produtos(
        db, filial_id, q=q, categoria_id=categoria_id, abaixo_minimo=abaixo_minimo
    )
    total = qry.count()
    linhas = (
        qry.order_by(Produto.nome.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_linha_out(r) for r in linhas], total


def resumo(
    db: Session,
    filial_id: int,
    *,
    q: str | None = None,
    categoria_id: int | None = None,
    abaixo_minimo: bool = False,
) -> EstoqueResumoOut:
    rows = _rows_produtos(
        db, filial_id, q=q, categoria_id=categoria_id, abaixo_minimo=abaixo_minimo
    ).all()
    total_itens = len(rows)
    itens_ativos = sum(1 for r in rows if r.ativo)
    total_bobinas = sum(1 for r in rows if r.dimensoes)
    abaixo = sum(1 for r in rows if _q(Decimal(r.saldo)) < _q(Decimal(r.estoque_minimo)))
    valor = sum(
        (_money(_q(Decimal(r.saldo)) * _money(Decimal(r.preco_custo))) for r in rows),
        Decimal("0.00"),
    )
    return EstoqueResumoOut(
        total_itens=total_itens,
        itens_ativos=itens_ativos,
        valor_total=_money(valor),
        total_bobinas=total_bobinas,
        abaixo_minimo=abaixo,
    )


def _kardex_out(mov: MovimentoEstoque, operador_nome: str | None, custo: Decimal) -> KardexOut:
    return KardexOut(
        id=mov.id,
        produto_id=mov.produto_id,
        tipo=mov.tipo,
        origem=mov.origem,
        documento_id=mov.documento_id,
        quantidade=_q(Decimal(mov.quantidade)),
        saldo_anterior=_q(Decimal(mov.saldo_anterior)),
        saldo_posterior=_q(Decimal(mov.saldo_posterior)),
        custo_unitario=custo,
        motivo=mov.motivo,
        operador_nome=operador_nome,
        criado_em=mov.criado_em,
    )


def listar_kardex(
    db: Session,
    filial_id: int,
    produto_id: int,
    *,
    tipo: TipoMovEstoque | None = None,
    data_inicio: datetime | None = None,
    data_fim: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[KardexOut], int]:
    produto = _buscar_produto(db, filial_id, produto_id)
    qry = (
        db.query(MovimentoEstoque, Usuario.nome.label("operador_nome"))
        .outerjoin(Usuario, Usuario.id == MovimentoEstoque.usuario_id)
        .filter(
            MovimentoEstoque.filial_id == filial_id,
            MovimentoEstoque.produto_id == produto_id,
        )
    )
    if tipo is not None:
        qry = qry.filter(MovimentoEstoque.tipo == tipo)
    if data_inicio is not None:
        qry = qry.filter(MovimentoEstoque.criado_em >= data_inicio)
    if data_fim is not None:
        qry = qry.filter(MovimentoEstoque.criado_em <= data_fim)
    total = qry.count()
    linhas = (
        qry.order_by(MovimentoEstoque.criado_em.desc(), MovimentoEstoque.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    custo = _money(Decimal(produto.preco_custo))
    return [_kardex_out(mov, operador, custo) for mov, operador in linhas], total


def movimentar(
    db: Session,
    filial_id: int,
    usuario_id: int,
    dados: MovimentarIn,
) -> tuple[KardexOut, Decimal]:
    if dados.tipo == TipoMovEstoque.AJUSTE and dados.quantidade < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ajuste, a quantidade deve ser o novo saldo físico (≥ 0).",
        )
    produto = _buscar_produto(db, filial_id, dados.produto_id)
    est = (
        db.query(ProdutoEstoque)
        .filter(
            ProdutoEstoque.filial_id == filial_id,
            ProdutoEstoque.produto_id == dados.produto_id,
        )
        .with_for_update()
        .first()
    )
    if est is None:
        est = ProdutoEstoque(filial_id=filial_id, produto_id=dados.produto_id)
        db.add(est)
        db.flush()
    anterior = _q(Decimal(est.saldo))
    qtd = _q(dados.quantidade)

    if dados.tipo == TipoMovEstoque.ENTRADA:
        novo = _q(anterior + qtd)
        lancado = qtd
    elif dados.tipo == TipoMovEstoque.SAIDA:
        novo = _q(anterior - qtd)
        if novo < 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Estoque insuficiente: saldo atual {anterior}, "
                    f"saída de {qtd}."
                ),
            )
        lancado = _q(-qtd)
    else:  # AJUSTE: quantidade é o novo saldo físico (contagem)
        novo = qtd
        lancado = _q(novo - anterior)

    est.saldo = novo
    est.atualizado_em = datetime.now(timezone.utc)
    mov = MovimentoEstoque(
        filial_id=filial_id,
        produto_id=dados.produto_id,
        tipo=dados.tipo,
        origem=OrigemMov.AJUSTE_MANUAL,
        documento_id=dados.documento_id,
        quantidade=lancado,
        saldo_anterior=anterior,
        saldo_posterior=novo,
        motivo=dados.motivo,
        usuario_id=usuario_id,
    )
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return _kardex_out(mov, None, _money(Decimal(produto.preco_custo))), novo


def reposicao(
    db: Session,
    filial_id: int,
    *,
    q: str | None = None,
    apenas_abaixo: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ReposicaoOut], int]:
    """Itens abaixo do mínimo com giro diário, autonomia e sugestão de lote."""
    corte = datetime.now(timezone.utc) - timedelta(days=_DIAS_JANELA)
    consumo_por_produto = {
        pid: Decimal(consumo or 0)
        for pid, consumo in db.query(
            MovimentoEstoque.produto_id,
            func.sum(func.abs(MovimentoEstoque.quantidade)).label("consumo"),
        )
        .filter(
            MovimentoEstoque.filial_id == filial_id,
            MovimentoEstoque.tipo == TipoMovEstoque.SAIDA,
            MovimentoEstoque.criado_em >= corte,
        )
        .group_by(MovimentoEstoque.produto_id)
        .all()
    }

    resultado: list[ReposicaoOut] = []
    for r in _rows_produtos(db, filial_id, q=q).all():
        saldo = _q(Decimal(r.saldo))
        minimo = _q(Decimal(r.estoque_minimo))
        if apenas_abaixo and not (saldo < minimo and minimo > 0):
            continue
        giro = _q(consumo_por_produto.get(r.produto_id, Decimal("0")) / Decimal(_DIAS_JANELA))
        autonomia = _q(saldo / giro) if giro > 0 else None
        alvo = _q(max(minimo, _q(giro * _LEAD_DIAS)))
        sugestao = _q(max(Decimal("0"), alvo - saldo))
        custo = _money(Decimal(r.preco_custo))
        resultado.append(
            ReposicaoOut(
                produto_id=r.produto_id,
                codigo=r.codigo,
                nome=r.nome,
                categoria_nome=r.categoria_nome,
                fornecedor_nome=None,
                saldo=saldo,
                estoque_minimo=minimo,
                giro_diario=giro,
                autonomia_dias=autonomia,
                sugestao=sugestao,
                custo_est=_money(sugestao * custo),
                status="critico" if saldo < minimo else "atencao",
            )
        )
    total = len(resultado)
    return resultado[offset : offset + limit], total