"""Serviços de Ordem de Serviço e Orçamento (PRD v2.0 §2.1, fluxo OS).

Regra central: orçamento e OS são registros de `ordem_servico` distinguidos por
`tipo`. A conversão de orçamento em OS cria um novo registro `os` com
`orcamento_origem_id` apontando para o orçamento e marca o original como
`convertido`. Todos os valores monetários são `Decimal` (nunca float).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.movimento import OrdemServico, OrdemServicoItem
from app.models.enums import StatusOs, TipoOs
from app.schemas.movimento import OsCreate, OsItemIn, OsItemOut, OsOut, OsUpdate

_TWO = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_TWO, rounding=ROUND_HALF_UP)


def _erro_integridade() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Dados inválidos: referência inexistente ou violação de unicidade.",
    )


def _montar_item(payload: OsItemIn, seq: int) -> OrdemServicoItem:
    total = _q(payload.valor_unitario * payload.quantidade - payload.desconto)
    if total < 0:
        total = Decimal("0.00")
    return OrdemServicoItem(
        seq=seq,
        produto_id=payload.produto_id,
        descricao_avulsa=payload.descricao_avulsa,
        quantidade=payload.quantidade.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        dimensoes=payload.dimensoes,
        valor_unitario=payload.valor_unitario,
        desconto=payload.desconto,
        valor_total=total,
    )


def _montar_itens(itens: list[OsItemIn]) -> list[OrdemServicoItem]:
    return [_montar_item(item, seq) for seq, item in enumerate(itens, start=1)]


def _totais(itens: list[OrdemServicoItem], desconto: Decimal) -> tuple[Decimal, Decimal]:
    valor_itens = _q(sum((i.valor_total for i in itens), Decimal("0")))
    if desconto > valor_itens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O desconto não pode ser maior que o valor dos itens.",
        )
    return valor_itens, _q(valor_itens - desconto)


def _para_out(os: OrdemServico) -> OsOut:
    dados = {c.name: getattr(os, c.name) for c in os.__table__.columns}
    dados["cliente_nome"] = os.cliente.nome_razao if os.cliente else None
    dados["vendedor_nome"] = os.vendedor.nome if os.vendedor else None
    dados["atendente_nome"] = os.atendente.nome if os.atendente else None
    dados["itens"] = [OsItemOut.model_validate(i) for i in os.itens]
    return OsOut.model_validate(dados)


def buscar(db: Session, os_id: int, *, filial_id: int) -> OrdemServico:
    os_obj = (
        db.query(OrdemServico)
        .options(
            joinedload(OrdemServico.cliente),
            joinedload(OrdemServico.vendedor),
            joinedload(OrdemServico.atendente),
            selectinload(OrdemServico.itens),
        )
        .filter(OrdemServico.id == os_id, OrdemServico.filial_id == filial_id)
        .first()
    )
    if not os_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de serviço não encontrada.",
        )
    return os_obj


def criar(db: Session, *, filial_id: int, usuario_id: int, dados: OsCreate) -> OsOut:
    itens = _montar_itens(dados.itens)
    valor_itens, valor_total = _totais(itens, dados.desconto)
    os_obj = OrdemServico(
        filial_id=filial_id,
        tipo=dados.tipo,
        status=StatusOs.ABERTO,
        cliente_id=dados.cliente_id,
        vendedor_id=dados.vendedor_id,
        atendente_id=dados.atendente_id,
        data_previsao_entrega=dados.data_previsao_entrega,
        desconto=dados.desconto,
        valor_itens=valor_itens,
        valor_total=valor_total,
        forma_pagamento=dados.forma_pagamento,
        observacoes=dados.observacoes,
        criado_por=usuario_id,
        itens=itens,
    )
    db.add(os_obj)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(os_obj)
    return _para_out(os_obj)


def atualizar(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    dados: OsUpdate,
) -> OsOut:
    os_obj = buscar(db, os_id, filial_id=filial_id)
    if os_obj.status in (StatusOs.ENTREGUE, StatusOs.CANCELADO, StatusOs.CONVERTIDO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ordem de serviço {os_obj.status.value} não pode ser alterada.",
        )

    campos = dados.model_dump(exclude_unset=True)

    for campo in ("cliente_id", "vendedor_id", "atendente_id", "forma_pagamento"):
        if campo in campos:
            setattr(os_obj, campo, campos[campo])
    if "data_previsao_entrega" in campos:
        os_obj.data_previsao_entrega = dados.data_previsao_entrega
    if "observacoes" in campos:
        os_obj.observacoes = dados.observacoes

    desconto = dados.desconto if "desconto" in campos else os_obj.desconto
    if "itens" in campos:
        if dados.itens is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A lista de itens não pode ser nula.",
            )
        os_obj.itens = _montar_itens(dados.itens)
    valor_itens, valor_total = _totais(os_obj.itens, desconto)
    os_obj.desconto = desconto
    os_obj.valor_itens = valor_itens
    os_obj.valor_total = valor_total

    db.commit()
    db.refresh(os_obj)
    return _para_out(os_obj)


_TRANSICOES: dict[StatusOs, set[StatusOs]] = {
    StatusOs.ABERTO: {StatusOs.APROVADO, StatusOs.PRODUCAO, StatusOs.PRONTA, StatusOs.ENTREGUE, StatusOs.CANCELADO},
    StatusOs.APROVADO: {StatusOs.PRODUCAO, StatusOs.PRONTA, StatusOs.ENTREGUE, StatusOs.CANCELADO},
    StatusOs.PRODUCAO: {StatusOs.PRONTA, StatusOs.ENTREGUE, StatusOs.CANCELADO},
    StatusOs.PRONTA: {StatusOs.ENTREGUE, StatusOs.CANCELADO},
    StatusOs.ENTREGUE: set(),
    StatusOs.CANCELADO: set(),
    StatusOs.CONVERTIDO: set(),
}


def mudar_status(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    novo: StatusOs,
) -> OsOut:
    os_obj = buscar(db, os_id, filial_id=filial_id)

    if os_obj.tipo == TipoOs.ORCAMENTO:
        permitidos: set[StatusOs] = {StatusOs.CANCELADO} if os_obj.status == StatusOs.ABERTO else set()
    else:
        permitidos = _TRANSICOES.get(os_obj.status, set())

    if novo not in permitidos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transição de status inválida: {os_obj.status.value} → {novo.value}.",
        )

    os_obj.status = novo
    hoje = date.today()
    if novo == StatusOs.PRONTA and not os_obj.data_conclusao:
        os_obj.data_conclusao = hoje
    if novo == StatusOs.ENTREGUE and not os_obj.data_entrega:
        os_obj.data_entrega = hoje
    db.commit()
    db.refresh(os_obj)
    return _para_out(os_obj)


def converter_em_os(db: Session, *, filial_id: int, orcamento_id: int) -> OsOut:
    orcamento = buscar(db, orcamento_id, filial_id=filial_id)
    if orcamento.tipo != TipoOs.ORCAMENTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Somente orçamentos podem ser convertidos em ordem de serviço.",
        )
    if orcamento.status != StatusOs.ABERTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Orçamento deve estar aberto para ser convertido em OS.",
        )

    nova = OrdemServico(
        filial_id=filial_id,
        tipo=TipoOs.OS,
        status=StatusOs.ABERTO,
        orcamento_origem_id=orcamento.id,
        cliente_id=orcamento.cliente_id,
        vendedor_id=orcamento.vendedor_id,
        atendente_id=orcamento.atendente_id,
        data_previsao_entrega=orcamento.data_previsao_entrega,
        desconto=orcamento.desconto,
        valor_itens=orcamento.valor_itens,
        valor_total=orcamento.valor_total,
        forma_pagamento=orcamento.forma_pagamento,
        observacoes=orcamento.observacoes,
        criado_por=orcamento.criado_por,
        itens=[
            OrdemServicoItem(
                seq=i.seq,
                produto_id=i.produto_id,
                descricao_avulsa=i.descricao_avulsa,
                quantidade=i.quantidade,
                dimensoes=i.dimensoes,
                valor_unitario=i.valor_unitario,
                desconto=i.desconto,
                valor_total=i.valor_total,
                executado=i.executado,
            )
            for i in orcamento.itens
        ],
    )
    orcamento.status = StatusOs.CONVERTIDO
    db.add(nova)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(nova)
    return _para_out(nova)


def cancelar(db: Session, *, filial_id: int, os_id: int) -> None:
    os_obj = buscar(db, os_id, filial_id=filial_id)
    if os_obj.status in (StatusOs.ENTREGUE, StatusOs.CANCELADO, StatusOs.CONVERTIDO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registro {os_obj.status.value} não pode ser cancelado.",
        )
    os_obj.status = StatusOs.CANCELADO
    db.commit()