"""Schemas Pydantic do módulo Estoque — consulta, kardex, movimentação manual e reposição."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MotivoAjuste, OrigemMov, TipoMovEstoque
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
    # Inventário rotativo: ajuste SEMPRE exige motivo (rastreabilidade).
    # A UI oferece um domínio fechado (MotivoAjuste); a API aceita texto livre
    # para compatibilidade com integrações, mas nunca vazio no ajuste.
    motivo: str | None = Field(default=None, max_length=255)
    documento_id: int | None = None

    @model_validator(mode="after")
    def _exigir_motivo_no_ajuste(self):
        if self.tipo == TipoMovEstoque.AJUSTE and not (self.motivo or "").strip():
            raise ValueError(
                "Ajuste de inventário exige motivo (perda, quebra, acerto ou contagem)."
            )
        return self


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


# ------------------------------------------------------- transferência (§5.6)


class TransferenciaIn(BaseModel):
    filial_destino_id: int
    produto_id: int
    quantidade: Decimal = Field(gt=0)
    observacoes: str | None = Field(default=None, max_length=500)


class TransferenciaOut(ORMModel):
    id: int
    numero: str
    filial_origem_id: int
    filial_destino_id: int
    produto_id: int
    quantidade: Decimal
    estado: str
    observacoes: str | None = None
    enviado_em: datetime
    recebido_em: datetime | None = None
    cancelado_em: datetime | None = None
