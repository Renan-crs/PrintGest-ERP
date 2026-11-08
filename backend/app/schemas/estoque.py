"""Schemas Pydantic do módulo Estoque — consulta, kardex, movimentação manual e reposição."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import OrigemMov, TipoMovEstoque
from app.schemas.common import ORMModel


class EstoqueLinhaOut(ORMModel):
    produto_id: int
    codigo: str
    nome: str
    categoria_id: int | None = None
    categoria_nome: str | None = None
    unidade: str
    dimensoes: str | None = None
    e_bobina: bool
    preco_custo: Decimal
    preco_venda: Decimal
    estoque_minimo: Decimal
    saldo: Decimal
    reservado: Decimal
    disponivel: Decimal
    valor_estoque: Decimal
    status: str
    ativo: bool


class EstoqueResumoOut(BaseModel):
    total_itens: int
    itens_ativos: int
    valor_total: Decimal
    total_bobinas: int
    abaixo_minimo: int


class MovimentarIn(BaseModel):
    produto_id: int
    tipo: TipoMovEstoque
    quantidade: Decimal = Field(
        gt=0, description="Qtde > 0; em Ajuste, é o novo saldo físico."
    )
    motivo: str | None = Field(default=None, max_length=255)
    documento_id: int | None = None


class KardexOut(ORMModel):
    id: int
    produto_id: int
    tipo: TipoMovEstoque
    origem: OrigemMov
    documento_id: int | None
    quantidade: Decimal
    saldo_anterior: Decimal
    saldo_posterior: Decimal
    custo_unitario: Decimal
    motivo: str | None
    operador_nome: str | None
    criado_em: datetime


class MovimentacaoOut(BaseModel):
    movimento: KardexOut
    saldo: Decimal


class ReposicaoOut(ORMModel):
    produto_id: int
    codigo: str
    nome: str
    categoria_nome: str | None = None
    fornecedor_nome: str | None = None
    saldo: Decimal
    estoque_minimo: Decimal
    giro_diario: Decimal
    autonomia_dias: Decimal | None
    sugestao: Decimal
    custo_est: Decimal
    status: str
