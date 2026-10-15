"""Regras de domínio para Precificação e Reajuste de Preços (PRD v2.1 §2.6).

Centraliza lógica de cálculo de preços, descontos, reajustes e margens.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from dataclasses import dataclass, field


# Tipos de reajuste
TIPO_REAJUSTE = Literal["percentual", "fixo"]


@dataclass(frozen=True)
class PrecoItem:
    """Representa um item de preço para simulação/aplicação."""
    produto_id: int
    codigo: str
    nome: str
    preco_atual: float
    preco_novo: float
    diferenca: float
    percentual: float
    bloqueado: bool = False
    motivo_bloqueio: str = ""


@dataclass
class SimulacaoReajuste:
    """Resultado de uma simulação de reajuste."""
    tipo: str  # "percentual" ou "fixo"
    valor: float  # percentual (ex: 10.0) ou valor fixo
    criterio: str  # "todos" ou "categoria:<id>"
    categoria_id: int | None = None
    itens_afetados: int = 0
    itens_bloqueados: int = 0
    valor_total_antes: float = 0.0
    valor_total_depois: float = 0.0
    itens: list = field(default_factory=list)


def calcular_preco_com_margem(custo: float, margem_percentual: float) -> float:
    """Calcula preço de venda baseado no custo e margem percentual desejada.
    
    Ex.: custo=100, margem=30% → preço = 100 / (1 - 0.30) = 142.86
    """
    if margem_percentual >= 100:
        raise ValueError("Margem deve ser menor que 100%")
    return round(Decimal(str(valor)) / (1 - Decimal(str(margem_percentual)) / 100), 2)


def calcular_margem(custo: float, preco_venda: float) -> float:
    """Calcula margem percentual real."""
    if preco_venda <= 0:
        return 0.0
    return round((1 - Decimal(str(custo)) / Decimal(str(preco_venda))) * 100, 2)


def aplicar_desconto(preco: float, desconto_percentual: float) -> float:
    """Aplica desconto percentual sobre preço."""
    if desconto_percentual <= 0:
        return preco
    return round(Decimal(str(preco)) * (1 - Decimal(str(desconto_percentual)) / 100), 2)


def aplicar_acrescimo(preco: float, acrescimo_percentual: float) -> float:
    """Aplica acréscimo percentual sobre preço."""
    if acrescimo_percentual <= 0:
        return preco
    return round(Decimal(str(preco)) * (1 + Decimal(str(acrescimo_percentual)) / 100), 2)


def simular_reajuste(
    itens: list[dict],
    tipo: str,  # "percentual" | "fixo"
    valor: float,
    criterio: str = "todos",  # "todos" | "categoria"
    categoria_id: int | None = None,
    bloqueados_reajuste: set[int] | None = None,
) -> dict:
    """Simula reajuste de preços em lote.
    
    Retorna dict com:
    - itens_afetados, itens_bloqueados
    - valor_total_antes, valor_total_depois
    - itens: lista de dicts com antes/depois por produto
    """
    bloqueados = bloqueados_reajuste or set()
    itens_afetados = 0
    itens_bloqueados = 0
    valor_antes = 0.0
    valor_depois = 0.0
    detalhes = []

    for item in itens:
        pid = item.get("produto_id") or item.get("id")
        preco_atual = float(item.get("preco_venda") or 0)
        bloqueado = pid in bloqueados

        if bloqueado:
            itens_bloqueados += 1
            detalhes.append({
                "produto_id": pid,
                "bloqueado": True,
                "preco_antes": preco_atual,
                "preco_depois": preco_atual,
                "motivo": "bloqueado_reajuste",
            })
            continue

        if criterio == "categoria":
            cat_id = item.get("categoria_id")
            if cat_id != categoria_id:
                detalhes.append({
                    "produto_id": pid,
                    "bloqueado": False,
                    "preco_antes": preco_atual,
                    "preco_depois": preco_atual,
                    "motivo": "categoria_nao_incluida",
                })
                continue

        # Calcula novo preço
        if tipo == "percentual":
            fator = 1 + (Decimal(str(valor)) / 100)
            novo_preco = round(Decimal(str(preco_atual)) * Decimal(str(fator)), 2)
        else:  # fixo
            novo_preco = round(Decimal(str(valor)), 2)

        valor_antes = float(preco_atual)
        valor_depois = float(novo_preco)

        itens_afetados += 1
        valor_antes_total += valor_antes
        valor_depois_total += valor_depois

        detalhes.append({
            "produto_id": pid,
            "bloqueado": False,
            "preco_antes": valor_antes,
            "preco_depois": valor_depois,
            "variacao": round(valor_depois - valor_antes, 2),
            "percentual_variacao": round((valor_depois - valor_antes) / valor_antes * 100, 2) if valor_antes else 0,
        })

    return {
        "total": len([i for i in detalhes if not i["bloqueado"]]),
        "afetados": itens_afetados,
        "bloqueados": itens_bloqueados,
        "valor_total_antes": round(valor_antes_total, 2),
        "valor_total_depois": round(valor_depois_total, 2),
        "diferenca_total": round(valor_depois_total - valor_antes_total, 2),
        "itens": detalhes,
    }


def aplicar_reajuste(
    itens: list[dict],
    tipo: str,
    valor: float,
    criterio: str = "todos",
    categoria_id: int | None = None,
    bloqueados: set[int] | None = None,
) -> list[dict]:
    """Aplica reajuste in-place nos itens (mutação). Retorna itens atualizados."""
    bloqueados = bloqueados or set()
    for item in itens:
        pid = item.get("produto_id") or item.get("id")
        if pid in bloqueados:
            continue
        if criterio == "categoria" and item.get("categoria_id") != categoria_id:
            continue
        
        preco_atual = float(item.get("preco_venda") or 0)
        if tipo == "percentual":
            fator = 1 + (Decimal(str(valor)) / 100)
            novo = round(Decimal(str(preco_atual)) * Decimal(str(fator)), 2)
        else:
            novo = round(Decimal(str(valor)), 2)
        
        item["preco_venda"] = str(novo)
        item["preco_anterior"] = str(item.get("preco_venda", preco_atual))
    
    return [i for i in itens if i.get("produto_id") or i.get("id")]


def calcular_markup(custo: float, preco_venda: float) -> float:
    """Markup = (PV - Custo) / Custo * 100"""
    if custo <= 0:
        return 0.0
    return round((Decimal(str(preco_venda)) - Decimal(str(custo))) / Decimal(str(custo)) * 100, 2)


def preco_com_imposto(preco_liquido: float, aliquota_icms: float, aliquota_ipi: float = 0,
                      aliquota_pis: float = 0, aliquota_cofins: float = 0) -> float:
    """Calcula preço com impostos (simplificado)."""
    total_impostos = aliquota_icms + aliquota_ipi + aliquota_pis + aliquota_cofins
    return round(Decimal(str(preco_liquido)) * (1 + Decimal(str(total_impostos)) / 100), 2)


def preco_sem_imposto(preco_com_imposto: float, aliquota_total: float) -> float:
    """Remove impostos do preço (engenharia reversa simplificada)."""
    return round(Decimal(str(preco_com_imposto)) / (1 + Decimal(str(aliquota_total)) / 100), 2)


__all__ = [
    "calcular_preco_com_margem",
    "calcular_margem",
    "aplicar_desconto",
    "aplicar_acrescimo",
    "simular_reajuste",
    "aplicar_reajuste",
    "calcular_markup",
    "preco_com_imposto",
    "preco_sem_imposto",
]