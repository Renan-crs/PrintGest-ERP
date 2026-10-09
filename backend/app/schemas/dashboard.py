"""Schemas do Dashboard (Tela Inicial) — resumo do dia por filial.

`DashboardResumoOut` é o payload de `GET /v1/dashboard/resumo`. Os campos
gerenciais (>= GERENTE) e operacionais (>= OPERADOR) são filtrados server-side
pelo serviço e chegam `null` para os demais níveis — sem penalizar a leitura.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DashboardVendaDiaOut(BaseModel):
    data: date
    valor: Decimal


class DashboardEntregaOut(BaseModel):
    """OS com prazo <= hoje, para a lista "Entregas de hoje e atrasadas"."""

    os_id: int
    numero: int
    cliente_nome: str | None = None
    servico: str | None = None
    prazo: date | None = None
    status: str
    atrasada: bool = False


class DashboardResumoOut(BaseModel):
    filial_nome: str | None = None
    vendas_hoje_qtd: int = 0
    vendas_hoje_valor: Decimal = Decimal("0")
    vendas_ontem_qtd: int = 0
    vendas_ontem_valor: Decimal = Decimal("0")
    os_abertas: int = 0
    os_prontas: int = 0
    # operacional (>= OPERADOR)
    projetos_em_producao: int | None = None
    projetos_atrasados: int | None = None
    estoque_abaixo_minimo: int | None = None
    entregas_hoje: list[DashboardEntregaOut] | None = None
    # gerencial (>= GERENTE)
    a_receber_vence_hoje: Decimal | None = None
    a_receber_atrasado: Decimal | None = None
    faturamento_previsto: list[DashboardVendaDiaOut] | None = None
    vendas_7_dias: list[DashboardVendaDiaOut] | None = None