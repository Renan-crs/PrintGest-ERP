"""Serviço da Venda de Balcão (PDV) — PRD v2.0 §2.1/§2.2, roadmap item 7.

Regra central (PRD §2.2 "baixa automática de estoque via `movimento_estoque`"):
ao confirmar uma venda de balcão, o sistema decrementa o saldo de cada produto
controlado por estoque na filial e registra o kardex (SAIDA / origem
`venda_balcao`) na MESMA transação. O cancelamento estorna (ENTRADA) devolvendo o
saldo. Valores sempre `Decimal`. Nível mínimo exigido: CAIXA (PRD §5 RBAC —
caixa PODE venda de balcão, ao contrário da OS).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import String, cast, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.cadastros import Cliente, MovimentoEstoque, Produto, ProdutoEstoque
from app.models.enums import FormaPagamento, OrigemMov, StatusVenda, TipoMovEstoque
from app.models.movimento import VendaBalcao, VendaBalcaoItem
from app.schemas.venda import (
    VendaCreate,
    VendaItemIn,
    VendaItemOut,
    VendaOut,
)

_TWO = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_TWO, rounding=ROUND_HALF_UP)


def _erro_integridade() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Dados inválidos: referência inexistente ou violação de unicidade.",
    )


def _montar_item(payload: VendaItemIn, seq: int) -> VendaBalcaoItem:
    total = _q(payload.valor_unitario * payload.quantidade - payload.desconto)
    if total < 0:
        total = Decimal("0.00")
    return VendaBalcaoItem(
        seq=seq,
        produto_id=payload.produto_id,
        descricao_avulsa=payload.descricao_avulsa,
        quantidade=payload.quantidade,
        valor_unitario=payload.valor_unitario,
        desconto=payload.desconto,
        valor_total=total,
    )


def _montar_itens(itens: list[VendaItemIn]) -> list[VendaBalcaoItem]:
    return [_montar_item(item, seq) for seq, item in enumerate(itens, start=1)]


def _totais(
    itens: list[VendaBalcaoItem], desconto: Decimal
) -> tuple[Decimal, Decimal]:
    valor_itens = _q(sum((i.valor_total for i in itens), Decimal("0")))
    if desconto > valor_itens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O desconto não pode ser maior que o valor dos itens.",
        )
    return valor_itens, _q(valor_itens - desconto)


def _para_out(venda: VendaBalcao) -> VendaOut:
    dados = {c.name: getattr(venda, c.name) for c in venda.__table__.columns}
    dados["cliente_nome"] = venda.cliente.nome_razao if venda.cliente else None
    dados["vendedor_nome"] = venda.vendedor.nome if venda.vendedor else None
    dados["operador_caixa_nome"] = (
        venda.operador.nome if venda.operador else None
    )
    dados["itens"] = [
        VendaItemOut(
            id=i.id,
            seq=i.seq,
            produto_id=i.produto_id,
            descricao_avulsa=i.descricao_avulsa,
            quantidade=i.quantidade,
            valor_unitario=i.valor_unitario,
            desconto=i.desconto,
            valor_total=i.valor_total,
        )
        for i in venda.itens
    ]
    return VendaOut.model_validate(dados)


def _baixar_estoque(
    db: Session,
    *,
    filial_id: int,
    venda: VendaBalcao,
    usuario_id: int | None,
) -> None:
    """Registra o kardex (SAIDA/ENTRADA) e atualiza o saldo de cada item."""
    for item in venda.itens:
        if item.produto_id is None:
            continue  # item avulso não movimenta estoque
        produto = db.get(Produto, item.produto_id)
        if produto is None or not produto.controla_estoque:
            continue

        est = (
            db.query(ProdutoEstoque)
            .filter(
                ProdutoEstoque.filial_id == filial_id,
                ProdutoEstoque.produto_id == item.produto_id,
            )
            .first()
        )
        if est is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Produto sem posição de estoque nesta filial. "
                    "Cadastre o estoque antes de vender."
                ),
            )
        anterior = est.saldo
        if venda.status == StatusVenda.OK and est.saldo < item.quantidade:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Estoque insuficiente do produto para concluir a venda."
                ),
            )

        if venda.status == StatusVenda.OK:
            est.saldo = _q(Decimal(est.saldo) - item.quantidade)
            tipo = TipoMovEstoque.SAIDA
        else:  # estorno por cancelamento
            est.saldo = _q(Decimal(est.saldo) + item.quantidade)
            tipo = TipoMovEstoque.ENTRADA

        db.add(
            MovimentoEstoque(
                filial_id=filial_id,
                produto_id=item.produto_id,
                tipo=tipo,
                origem=OrigemMov.VENDA_BALCAO,
                documento_id=venda.id,
                quantidade=item.quantidade,
                saldo_anterior=anterior,
                saldo_posterior=est.saldo,
                motivo="Venda de balcão" if venda.status == StatusVenda.OK
                else "Estorno por cancelamento de venda de balcão",
                usuario_id=usuario_id,
            )
        )


def criar(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    dados: VendaCreate,
) -> VendaOut:
    itens = _montar_itens(dados.itens)
    valor_itens, valor_total = _totais(itens, dados.desconto)

    venda = VendaBalcao(
        filial_id=filial_id,
        status=StatusVenda.OK,
        cliente_id=dados.cliente_id,
        vendedor_id=dados.vendedor_id,
        operador_caixa=usuario_id,
        data_venda=dados.data_venda,
        valor_itens=valor_itens,
        desconto=dados.desconto,
        valor_total=valor_total,
        forma_pagamento=dados.forma_pagamento,
        parcelas=dados.parcelas,
        observacoes=dados.observacoes,
        itens=itens,
    )
    db.add(venda)
    try:
        db.flush()  # garante venda.id para o kardex antes do commit
        _baixar_estoque(db, filial_id=filial_id, venda=venda, usuario_id=usuario_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(venda)
    return _para_out(venda)


def buscar(db: Session, venda_id: int, *, filial_id: int) -> VendaBalcao:
    venda = (
        db.query(VendaBalcao)
        .options(
            joinedload(VendaBalcao.cliente),
            joinedload(VendaBalcao.vendedor),
            joinedload(VendaBalcao.operador),
            selectinload(VendaBalcao.itens),
        )
        .filter(VendaBalcao.id == venda_id, VendaBalcao.filial_id == filial_id)
        .first()
    )
    if not venda:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venda de balcão não encontrada.",
        )
    return venda


def listar(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    status_venda: StatusVenda | None = None,
    forma_pagamento: FormaPagamento | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[VendaOut], int]:
    base = db.query(VendaBalcao).filter(VendaBalcao.filial_id == filial_id)
    if status_venda:
        base = base.filter(VendaBalcao.status == status_venda)
    if forma_pagamento:
        base = base.filter(VendaBalcao.forma_pagamento == forma_pagamento)
    if data_inicio:
        base = base.filter(VendaBalcao.data_venda >= data_inicio)
    if data_fim:
        base = base.filter(VendaBalcao.data_venda <= data_fim)
    if q:
        termo = f"%{q.strip()}%"
        base = base.outerjoin(
            Cliente, VendaBalcao.cliente_id == Cliente.id
        ).filter(
            or_(
                Cliente.nome_razao.ilike(termo),
                cast(VendaBalcao.numero, String).ilike(termo),
            )
        )
    total = base.count()
    itens = (
        base.options(
            joinedload(VendaBalcao.cliente),
            joinedload(VendaBalcao.vendedor),
            joinedload(VendaBalcao.operador),
            selectinload(VendaBalcao.itens),
        )
        .order_by(VendaBalcao.numero.desc())
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
        .all()
    )
    return [_para_out(v) for v in itens], total


def cancelar(db: Session, *, filial_id: int, venda_id: int) -> None:
    venda = buscar(db, venda_id, filial_id=filial_id)
    if venda.status == StatusVenda.CANCELADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Venda de balcão já cancelada.",
        )
    venda.status = StatusVenda.CANCELADO
    _baixar_estoque(db, filial_id=filial_id, venda=venda, usuario_id=None)
    db.commit()
