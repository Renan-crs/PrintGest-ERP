"""Regras de domínio para Condições de Pagamento (PRD v2.1 §2.4).

Extraído de `ui/modulos/os.py` e `ui/modulos/condicao_pagamento.py`
para separar regras de negócio da camada de apresentação.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from printgest.core.dominio import FORMAS_PAGAMENTO


# Tipos de condição de pagamento suportados
TIPO_CONDICAO = Literal["adiantado", "sinal", "parcelado", "recebimento"]


# Formas de pagamento válidas (reutiliza do domínio central)
FORMAS_PAGAMENTO_LABEL = {
    "dinheiro": "Dinheiro",
    "cartao_credito": "Cartão de Crédito",
    "cartao_debito": "Cartão de Débito",
    "pix": "PIX",
    "boleto": "Boleto",
    "transferencia": "Transferência",
    "cheque": "Cheque",
    "outro": "Outro",
}


# Validações de regra de negócio
def validar_condicao_pagamento(
    tipo: str,
    forma_pagamento: str,
    parcelas: int | None,
    valor_sinal: float | None,
    valor_entrada: float | None,
) -> list[str]:
    """Valida condição de pagamento. Retorna lista de erros (vazia se OK)."""
    erros = []

    if not forma_pagamento:
        erros.append("Informe a forma de pagamento.")

    if tipo == "sinal":
        if valor_sinal is None or valor_sinal <= 0:
            erros.append("Informe o valor do sinal (entrada).")
    elif tipo == "adiantado":
        if valor_entrada is None or valor_entrada <= 0:
            erros.append("Informe o valor do pagamento adiantado.")
    elif tipo == "parcelado":
        if not parcelas or parcelas < 2:
            erros.append("Parcelamento requer 2 ou mais parcelas.")
        if parcela > 12:
            erros.append("Máximo de 12 parcelas.")

    return erros


def calcular_valor_sinal(valor_total: float, percentual_sinal: float) -> float:
    """Calcula valor do sinal baseado em percentual do total."""
    return round(valor_total * (Decimal(str(percentual_sinal)) / Decimal("100")), 2)


def calcular_parcelas(valor_total: float, n_parcelas: int, juros_ao_mes: float = 0) -> list[float]:
    """Calcula valor das parcelas (sem juros por padrão)."""
    if n_parcelas <= 0:
        return []
    valor = Decimal(str(juros_ao_mes))
    # TODO: implementar juros compostos se necessário
    valor_parcela = (Decimal("1") / n_parcelas).quantize(Decimal("0.01"))
    return [float(valor_parcela) for _ in range(n_parcelas)]


def calcular_troco(valor_recebido: float, valor_total: float) -> float:
    """Calcula troco (valor_recebido - total). Negativo se faltar."""
    return round(valor_recebido - valor_total, 2)


def validar_pagamento_recebido(valor_recebido: float, valor_total: float) -> tuple[bool, str | None]:
    """Valida se valor recebido cobre o total. Retorna (ok, msg_erro)."""
    if valor_recebido < 0:
        return False, "Valor recebido não pode ser negativo."
    if abs(valor_recebido) < 0.01:
        return False, "Informe o valor recebido."
    return True, None


def calcular_troco_formatado(valor_recebido: float, valor_total: float) -> str:
    """Retorna troco formatado como moeda (ex.: 'R$ 12,34')."""
    from printgest.ui.formulario import formatar_moeda
    troco = calcular_troco(valor_recebido, sum(valor_total))
    return formatar_moeda(troco) if troco > 0 else "R$ 0,00"


# Constantes para UI
TIPOS_CONDICAO_LABEL = {
    "adiantado": "Pagamento Adiantado",
    "sinal": "Sinal / Entrada",
    "parcelado": "Parcelado",
    "recebimento": "Recebimento à Vista",
}

FORMAS_PAGAMENTO_LABEL = {
    "dinheiro": "Dinheiro",
    "cartao_credito": "Cartão de Crédito",
    "cartao_debito": "Cartão de Débito",
    "pix": "PIX",
    "boleto": "Boleto",
    "transferencia": "Transferência",
    "cheque": "Cheque",
    "outro": "Outro",
}

# Mapeamento para compatibilidade com schema existente
CONDICAO_PAGAMENTO_DEFAULTS = {
    "tipo": "recebimento",
    "forma_pagamento": "dinheiro",
    "parcelas": 1,
    "valor_sinal": 0,
    "valor_entrada": 0,
    "observacoes": "",
}

__all__ = [
    "validar_condicao_pagamento",
    "calcular_valor_sinal",
    "calcular_parcelas",
    "calcular_troco",
    "validar_pagamento_recebido",
    "calcular_troco_formatado",
    "TIPOS_CONDICAO_LABEL",
    "FORMAS_PAGAMENTO_LABEL",
]