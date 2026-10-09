"""Pagamento antecipado / sinal de clientes (PRD tela 2.1).

Um cliente pode exigir recebimento antecipado ao abrir uma O.S. ou uma venda de
balcão:
  - `pagamento_adiantado`: 100% do valor total;
  - `sinal`: percentual (`sinal_pct`) do valor total.
Orçamentos são gratuitos e não passam por esta regra.

Quando a exigência existe, `exigir_e_registrar` valida a confirmação do
operador e grava o lançamento financeiro: uma `conta_receber` já baixada
(paga) e, se o operador tiver um caixa aberto, o `movimento_caixa` de entrada
correspondente — tudo na mesma transação do documento.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.cadastros import Cliente
from app.models.enums import StatusCaixa, StatusConta, TipoMovCaixa
from app.models.financeiro import Caixa, ContaReceber, MovimentoCaixa

_TWO = Decimal("0.01")
_CEM = Decimal("100")


def _q(valor: Decimal) -> Decimal:
    return Decimal(valor).quantize(_TWO, rounding=ROUND_HALF_UP)


def _brl(valor: Decimal) -> str:
    return f"R$ {_q(valor):.2f}".replace(".", ",")


def _fmt_pct(pct: Decimal) -> str:
    texto = f"{Decimal(pct):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",") if texto else "0"


def exigencia(cliente: Cliente | None, valor_total) -> tuple[str, Decimal] | None:
    """Condição exigida do cliente como `(rótulo, valor)`; `None` se não houver.

    Retorna `None` também quando o valor devido é zero (não há o que receber).
    """
    if cliente is None:
        return None
    total = _q(Decimal(valor_total or 0))
    if cliente.pagamento_adiantado:
        return ("pagamento adiantado (total)", total)
    if cliente.sinal:
        pct = Decimal(cliente.sinal_pct or 0)
        return (f"sinal de {_fmt_pct(pct)}%", _q(total * pct / _CEM))
    return None


def exigir_e_registrar(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    cliente: Cliente | None,
    valor_total,
    confirmado: bool,
    documento: str,
    ordem_servico_id: int | None = None,
    venda_balcao_id: int | None = None,
) -> ContaReceber | None:
    """Aplica a regra do cliente e grava o lançamento financeiro do recebimento.

    Levanta `400` quando o cliente exige adiantamento/sinal e o operador não
    confirmou o recebimento. Caso contrário cria a conta a receber já baixada
    (`status=paga`) e, havendo caixa aberto do operador, o movimento de entrada.
    """
    regra = exigencia(cliente, valor_total)
    if regra is None:
        return None

    rotulo, valor = regra
    if valor <= 0:
        return None

    if not confirmado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"O cliente exige {rotulo}. Confirme o recebimento de "
                f"{_brl(valor)} para criar este registro."
            ),
        )

    descricao = f"Adiantamento — {documento} ({rotulo})"
    conta = ContaReceber(
        filial_id=filial_id,
        cliente_id=cliente.id,
        ordem_servico_id=ordem_servico_id,
        venda_balcao_id=venda_balcao_id,
        descricao=descricao,
        vencimento=date.today(),
        valor=valor,
        valor_pago=valor,
        status=StatusConta.PAGA,
        data_pagamento=date.today(),
        usuario_baixa_id=usuario_id,
    )
    db.add(conta)
    db.flush()  # garante conta.id para o movimento de caixa

    caixa = (
        db.query(Caixa)
        .filter(
            Caixa.filial_id == filial_id,
            Caixa.usuario_id == usuario_id,
            Caixa.status == StatusCaixa.ABERTO,
        )
        .first()
    )
    if caixa is not None:
        db.add(
            MovimentoCaixa(
                caixa_id=caixa.id,
                tipo=TipoMovCaixa.ENTRADA,
                conta_receber_id=conta.id,
                descricao=descricao,
                valor=valor,
                usuario_id=usuario_id,
            )
        )
    return conta
