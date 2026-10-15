"""Domínio de negócio — regras puras, sem dependência de UI ou framework.

Módulos:
- ordem_servico: regras de OS/Orçamento (status, transições, validações)
- pagamento: condições de pagamento, sinais, parcelas
- precificacao: precificação, margens, reajustes, impostos
"""

from printgest.core.dominio.ordem_servico import (
    StatusOs,
    TipoOs,
    rotulo_status,
    proximo_status,
    validar_transicao,
    rotulo_proximo_status,
    validar_os_criacao,
    validar_transicao_status,
    calcular_valor_total,
    FORMAS_PAGAMENTO,
    FORMA_PAGAMENTO_LABEL,
    STATUS_CLASSE,
    STATUS_ORDEM,
    TIPOS_OS,
    status_badge_class,
    ordenar_por_status,
)

from printgest.core.dominio.pagamento import (
    validar_condicao_pagamento,
    calcular_valor_sinal,
    calcular_parcelas,
    calcular_troco,
    validar_pagamento_recebido,
    calcular_troco_formatado,
    TIPOS_CONDICAO_LABEL,
    FORMAS_PAGAMENTO_LABEL,
)

from printgest.core.dominio.precificacao import (
    calcular_preco_com_margem,
    calcular_margem,
    aplicar_desconto,
    aplicar_acrescimo,
    simular_reajuste,
    aplicar_reajuste,
    calcular_markup,
    preco_com_imposto,
    preco_sem_imposto,
)

__all__ = [
    # ordem_servico
    "StatusOs",
    "TipoOs",
    "rotulo_status",
    "proximo_status",
    "validar_transicao",
    "rotulo_proximo_status",
    "validar_os_criacao",
    "validar_transicao_status",
    "calcular_valor_total",
    "FORMAS_PAGAMENTO",
    "FORMA_PAGAMENTO_LABEL",
    "STATUS_CLASSE",
    "STATUS_ORDEM",
    "TIPOS_OS",
    "status_badge_class",
    "ordenar_por_status",
    # pagamento
    "validar_condicao_pagamento",
    "calcular_valor_sinal",
    "calcular_parcelas",
    "calcular_troco",
    "validar_pagamento_recebido",
    "calcular_troco_formatado",
    "TIPOS_CONDICAO_LABEL",
    "FORMAS_PAGAMENTO_LABEL",
    # precificacao
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