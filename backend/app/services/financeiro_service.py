"""Serviços do módulo Financeiro (PRD §1.3 / telas_e_fluxos §1.5 e §2.4).

- **Caixa**: abertura, extrato (movimentos), sangria/suprimento e fechamento com
  conferência (`valor_esperado` × `valor_informado` → `diferenca`).
- **Contas a receber/pagar**: listagem com busca e baixa de pagamento. As contas
  nascem dos documentos de movimento (venda/OS/pedido) e dos adiantamentos — a
  tela não as cria.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.cadastros import Cliente, Fornecedor
from app.models.enums import StatusCaixa, StatusConta, TipoMovCaixa
from app.models.financeiro import Caixa, ContaPagar, ContaReceber, MovimentoCaixa

_TWO = Decimal("0.01")
_ENTRADAS = (TipoMovCaixa.ENTRADA, TipoMovCaixa.SUPRIMENTO)
_SAIDAS = (TipoMovCaixa.SAIDA, TipoMovCaixa.SANGRIA)


def _q(valor) -> Decimal:
    return Decimal(valor or 0).quantize(_TWO, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------- caixa
def caixa_aberto(db: Session, *, filial_id: int, usuario_id: int) -> Caixa | None:
    return (
        db.query(Caixa)
        .filter(
            Caixa.filial_id == filial_id,
            Caixa.usuario_id == usuario_id,
            Caixa.status == StatusCaixa.ABERTO,
        )
        .first()
    )


def _totais(db: Session, caixa: Caixa) -> tuple[Decimal, Decimal]:
    movimentos = db.query(MovimentoCaixa).filter(MovimentoCaixa.caixa_id == caixa.id).all()
    entradas = sum((_q(m.valor) for m in movimentos if m.tipo in _ENTRADAS), Decimal("0"))
    saidas = sum((_q(m.valor) for m in movimentos if m.tipo in _SAIDAS), Decimal("0"))
    return entradas, saidas


def caixa_out(db: Session, caixa: Caixa) -> dict:
    entradas, saidas = _totais(db, caixa)
    esperado = _q(caixa.valor_abertura) + entradas - saidas
    return {
        "id": caixa.id,
        "filial_id": caixa.filial_id,
        "usuario_id": caixa.usuario_id,
        "status": caixa.status,
        "data_abertura": caixa.data_abertura,
        "valor_abertura": _q(caixa.valor_abertura),
        "data_fechamento": caixa.data_fechamento,
        "valor_esperado": caixa.valor_esperado,
        "valor_informado": caixa.valor_informado,
        "diferenca": caixa.diferenca,
        "observacoes": caixa.observacoes,
        "total_entradas": entradas,
        "total_saidas": saidas,
        "saldo_atual": esperado,
    }


def abrir_caixa(db: Session, *, filial_id: int, usuario_id: int, dados) -> Caixa:
    if caixa_aberto(db, filial_id=filial_id, usuario_id=usuario_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um caixa aberto para este usuário. Feche-o antes de abrir outro.",
        )
    caixa = Caixa(
        filial_id=filial_id,
        usuario_id=usuario_id,
        status=StatusCaixa.ABERTO,
        valor_abertura=_q(dados.valor_abertura),
        observacoes=dados.observacoes,
    )
    db.add(caixa)
    db.commit()
    db.refresh(caixa)
    return caixa


def _obter_caixa(db: Session, caixa_id: int, filial_id: int) -> Caixa:
    caixa = (
        db.query(Caixa)
        .filter(Caixa.id == caixa_id, Caixa.filial_id == filial_id)
        .first()
    )
    if caixa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Caixa não encontrado."
        )
    return caixa


def registrar_movimento(db: Session, *, caixa_id: int, filial_id: int, dados) -> MovimentoCaixa:
    if dados.tipo not in (TipoMovCaixa.SANGRIA, TipoMovCaixa.SUPRIMENTO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lançamento manual aceita apenas sangria ou suprimento.",
        )
    caixa = _obter_caixa(db, caixa_id, filial_id)
    if caixa.status != StatusCaixa.ABERTO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O caixa está fechado; não é possível lançar movimentos.",
        )
    movimento = MovimentoCaixa(
        caixa_id=caixa.id,
        tipo=dados.tipo,
        descricao=dados.descricao or dados.tipo.value.capitalize(),
        valor=_q(dados.valor),
        usuario_id=caixa.usuario_id,
    )
    db.add(movimento)
    db.commit()
    db.refresh(movimento)
    return movimento


def fechar_caixa(db: Session, *, caixa_id: int, filial_id: int, usuario_id: int, dados) -> Caixa:
    caixa = _obter_caixa(db, caixa_id, filial_id)
    if caixa.status != StatusCaixa.ABERTO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Este caixa já está fechado."
        )
    entradas, saidas = _totais(db, caixa)
    esperado = _q(caixa.valor_abertura) + entradas - saidas
    informado = _q(dados.valor_informado)
    caixa.valor_esperado = esperado
    caixa.valor_informado = informado
    caixa.diferenca = informado - esperado
    caixa.status = StatusCaixa.FECHADO
    caixa.data_fechamento = datetime.now(timezone.utc)
    caixa.closed_user_id = usuario_id
    if dados.observacoes:
        caixa.observacoes = dados.observacoes
    db.commit()
    db.refresh(caixa)
    return caixa


def listar_movimentos(
    db: Session, *, caixa_id: int, filial_id: int, limit: int = 200, offset: int = 0
) -> tuple[list[MovimentoCaixa], int]:
    _obter_caixa(db, caixa_id, filial_id)  # 404 se não for da filial
    query = db.query(MovimentoCaixa).filter(MovimentoCaixa.caixa_id == caixa_id)
    total = query.count()
    itens = (
        query.order_by(MovimentoCaixa.criado_em.desc(), MovimentoCaixa.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return itens, total


# -------------------------------------------------------------------- contas
def _contas_receber_query(db: Session, filial_id: int):
    return (
        db.query(ContaReceber, Cliente.nome_razao)
        .outerjoin(Cliente, ContaReceber.cliente_id == Cliente.id)
        .filter(ContaReceber.filial_id == filial_id)
    )


def listar_contas_receber(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    status_conta: StatusConta | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = _contas_receber_query(db, filial_id)
    if status_conta is not None:
        query = query.filter(ContaReceber.status == status_conta)
    termo = (q or "").strip()
    if termo:
        query = query.filter(
            or_(
                ContaReceber.descricao.ilike(f"%{termo}%"),
                Cliente.nome_razao.ilike(f"%{termo}%"),
            )
        )
    total = query.count()
    linhas = (
        query.order_by(ContaReceber.vencimento.asc(), ContaReceber.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    dados = []
    for conta, nome in linhas:
        item = {c.name: getattr(conta, c.name) for c in ContaReceber.__table__.columns}
        item["cliente_nome"] = nome
        dados.append(item)
    return dados, total


def listar_contas_pagar(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    status_conta: StatusConta | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = (
        db.query(ContaPagar, Fornecedor.nome_razao)
        .outerjoin(Fornecedor, ContaPagar.fornecedor_id == Fornecedor.id)
        .filter(ContaPagar.filial_id == filial_id)
    )
    if status_conta is not None:
        query = query.filter(ContaPagar.status == status_conta)
    termo = (q or "").strip()
    if termo:
        query = query.filter(
            or_(
                ContaPagar.descricao.ilike(f"%{termo}%"),
                Fornecedor.nome_razao.ilike(f"%{termo}%"),
            )
        )
    total = query.count()
    linhas = (
        query.order_by(ContaPagar.vencimento.asc(), ContaPagar.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    dados = []
    for conta, nome in linhas:
        item = {c.name: getattr(conta, c.name) for c in ContaPagar.__table__.columns}
        item["fornecedor_nome"] = nome
        dados.append(item)
    return dados, total


def _obter_conta(db: Session, model, item_id: int, filial_id: int):
    conta = db.query(model).filter(model.id == item_id, model.filial_id == filial_id).first()
    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada."
        )
    return conta


def _baixar(db: Session, *, conta, usuario_id: int, dados) -> dict:
    if conta.status == StatusConta.PAGA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Esta conta já foi baixada."
        )
    if conta.status == StatusConta.CANCELADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Conta cancelada não recebe baixa."
        )
    saldo = _q(conta.valor) - _q(conta.valor_pago)
    pago_agora = _q(dados.valor_pago) if dados.valor_pago is not None else saldo
    if pago_agora <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Informe um valor de baixa maior que zero."
        )
    if pago_agora > saldo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O valor da baixa excede o saldo devedor (R$ {saldo:.2f}).",
        )
    conta.valor_pago = _q(conta.valor_pago) + pago_agora
    conta.data_pagamento = dados.data_pagamento or date.today()
    conta.usuario_baixa_id = usuario_id
    if pago_agora >= saldo:
        conta.status = StatusConta.PAGA
    if dados.observacoes:
        conta.observacoes = dados.observacoes
    db.commit()
    db.refresh(conta)
    return conta


def baixar_conta_receber(db: Session, *, conta_id: int, filial_id: int, usuario_id: int, dados) -> dict:
    conta = _obter_conta(db, ContaReceber, conta_id, filial_id)
    conta = _baixar(db, conta=conta, usuario_id=usuario_id, dados=dados)
    nome = None
    if conta.cliente_id:
        cliente = db.get(Cliente, conta.cliente_id)
        nome = cliente.nome_razao if cliente else None
    item = {c.name: getattr(conta, c.name) for c in ContaReceber.__table__.columns}
    item["cliente_nome"] = nome
    return item


def baixar_conta_pagar(db: Session, *, conta_id: int, filial_id: int, usuario_id: int, dados) -> dict:
    conta = _obter_conta(db, ContaPagar, conta_id, filial_id)
    conta = _baixar(db, conta=conta, usuario_id=usuario_id, dados=dados)
    nome = None
    if conta.fornecedor_id:
        fornecedor = db.get(Fornecedor, conta.fornecedor_id)
        nome = fornecedor.nome_razao if fornecedor else None
    item = {c.name: getattr(conta, c.name) for c in ContaPagar.__table__.columns}
    item["fornecedor_nome"] = nome
    return item
