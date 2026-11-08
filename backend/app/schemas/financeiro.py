"""Schemas do módulo Financeiro (PRD §1.3 — caixa, contas a pagar/receber, plano de contas).

As contas a receber/pagar não são criadas pela tela: nascem dos documentos de
movimento (O.S., venda balcão, pedido de compra) e dos adiantamentos/sinais. A
tela Financeiro lista e dá **baixa** nelas.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.enums import (
    StatusCaixa,
    StatusConta,
    TipoMovCaixa,
    TipoPlanoConta,
)
from app.schemas.common import ORMModel


# --------------------------------------------------------------------- plano
class PlanoContaBase(ORMModel):
    codigo: str = Field(min_length=1, max_length=20)
    nome: str = Field(min_length=1, max_length=120)
    tipo: TipoPlanoConta
    pai_id: int | None = None
    ativo: bool = True


class PlanoContaCreate(PlanoContaBase):
    pass


class PlanoContaUpdate(ORMModel):
    codigo: str | None = Field(default=None, min_length=1, max_length=20)
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    tipo: TipoPlanoConta | None = None
    pai_id: int | None = None
    ativo: bool | None = None


class PlanoContaOut(PlanoContaBase):
    id: int
    filial_id: int


# --------------------------------------------------------------------- caixa
class MovimentoCaixaOut(ORMModel):
    id: int
    caixa_id: int
    tipo: TipoMovCaixa
    descricao: str | None = None
    valor: Decimal
    venda_balcao_id: int | None = None
    conta_receber_id: int | None = None
    conta_pagar_id: int | None = None
    usuario_id: int | None = None
    criado_em: datetime


class CaixaOut(ORMModel):
    id: int
    filial_id: int
    usuario_id: int
    status: StatusCaixa
    data_abertura: datetime
    valor_abertura: Decimal
    data_fechamento: datetime | None = None
    valor_esperado: Decimal | None = None
    valor_informado: Decimal | None = None
    diferenca: Decimal | None = None
    observacoes: str | None = None
    # Calculados na leitura (não persistidos): situação do extrato.
    total_entradas: Decimal = Decimal(0)
    total_saidas: Decimal = Decimal(0)
    saldo_atual: Decimal = Decimal(0)


class AbrirCaixaIn(ORMModel):
    valor_abertura: Decimal = Field(default=Decimal(0), ge=0)
    observacoes: str | None = None


class FecharCaixaIn(ORMModel):
    valor_informado: Decimal = Field(ge=0)
    observacoes: str | None = None


class MovimentoCaixaIn(ORMModel):
    tipo: TipoMovCaixa
    valor: Decimal = Field(gt=0)
    descricao: str | None = Field(default=None, max_length=255)


# -------------------------------------------------------------------- contas
class BaixaIn(ORMModel):
    """Baixa (total ou parcial) de uma conta a receber/pagar."""

    valor_pago: Decimal | None = Field(default=None, gt=0)
    data_pagamento: date | None = None
    observacoes: str | None = None


class ContaReceberOut(ORMModel):
    id: int
    filial_id: int
    cliente_id: int | None = None
    cliente_nome: str | None = None
    plano_conta_id: int | None = None
    venda_balcao_id: int | None = None
    ordem_servico_id: int | None = None
    descricao: str
    parcela: int
    total_parcelas: int
    vencimento: date
    valor: Decimal
    valor_pago: Decimal
    status: StatusConta
    data_pagamento: date | None = None
    usuario_baixa_id: int | None = None
    observacoes: str | None = None
    created_at: datetime


class ContaPagarOut(ORMModel):
    id: int
    filial_id: int
    fornecedor_id: int | None = None
    fornecedor_nome: str | None = None
    plano_conta_id: int | None = None
    pedido_compra_id: int | None = None
    descricao: str
    parcela: int
    total_parcelas: int
    vencimento: date
    valor: Decimal
    valor_pago: Decimal
    status: StatusConta
    data_pagamento: date | None = None
    usuario_baixa_id: int | None = None
    observacoes: str | None = None
    created_at: datetime
