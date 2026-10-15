"""Regras de domínio para Ordem de Serviço / Orçamento (PRD v2.1 §2.1).

Extraído de `ui/modulos/os.py` para separar regras de negócio da camada de apresentação.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

# FORMAS_PAGAMENTO definida localmente para evitar import circular
FORMAS_PAGAMENTO = [
    ("dinheiro", "Dinheiro"),
    ("cartao_credito", "Cartão de Crédito"),
    ("cartao_debito", "Cartão de Débito"),
    ("pix", "PIX"),
    ("boleto", "Boleto"),
    ("transferencia", "Transferência"),
    ("cheque", "Cheque"),
    ("outro", "Outro"),
]


class StatusOs(StrEnum):
    ABERTO = "aberto"
    APROVADO = "aprovado"
    PRODUCAO = "producao"
    PRONTA = "pronta"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"
    CONVERTIDO = "convertido"


class TipoOs(StrEnum):
    ORCAMENTO = "orcamento"
    OS = "os"


# Transições válidas de status (regra de negócio centralizada)
# Ordem: aberto → aprovado → producao → pronta → entregue
# Cancelado pode vir de qualquer estado (exceto convertido)
# Convertido é terminal (orçamento virou OS)
_PROXIMO_STATUS: dict[str, str] = {
    "aberto": "aprovado",
    "aprovado": "producao",
    "producao": "pronta",
    "pronta": "entregue",
}

# Mapeamento código → rótulo amigável
_ROTULO_STATUS = {
    "aberto": "Aberto",
    "aprovado": "Aprovado",
    "producao": "Em produção",
    "pronta": "Pronta",
    "entregue": "Entregue",
    "cancelado": "Cancelado",
    "convertido": "Convertido",
}

# Status aplicado ao soltar um cartão em cada coluna. "Aguardando" agrupa
# `aberto`/`aprovado`; como não há transição *para trás* até essa etapa (o
# backend recusa), o alvo é apenas nominal — a mensagem de erro cobre o caso.
_STATUS_DESTINO = {
    "aguardando": "aprovado",
    "producao": "producao",
    "pronta": "pronta",
    "entregue": "entregue",
}


# Etapas do quadro de Projetos. "Aguardando" agrupa `aberto` e `aprovado` — o
# orçamento aprovado ainda não entrou em produção (ver docs/revisao_projetos.md).
_COLUNAS_QUADRO = [
    ("aguardando", "Aguardando", ("aberto", "aprovado")),
    ("producao", "Em produção", ("producao",)),
    ("pronta", "Prontas", ("pronta",)),
    ("entregue", "Entregues", ("entregue",)),
]


def rotulo_status(status: str) -> str:
    """Converte código de status para rótulo amigável."""
    return _ROTULO_STATUS.get(status, status)


def proximo_status(status_atual: str) -> str | None:
    """Retorna o próximo status válido na transição, ou None se não houver."""
    return _PROXIMO_STATUS.get(status_atual)


def validar_transicao(status_atual: str, status_novo: str) -> bool:
    """Valida se a transição de status é permitida pelas regras de negócio."""
    if status_novo == "cancelado":
        return status_atual != "entregue" and status_atual != "convertido"
    proximo = _PROXIMO_STATUS.get(status_atual)
    return status_novo == proximo


def rotulo_proximo_status(status_atual: str) -> str:
    """Rótulo amigável do próximo status (para botões de ação)."""
    proximo = proximo_status(status_atual)
    return rotulo_status(proximo) if proximo else "—"


# Aliases para compatibilidade com código existente
_rotulo_status = rotulo_status
_rotulo_proximo_status = rotulo_proximo_status


# Regras de validação de formulário OS/Orçamento
def validar_os_criacao(
    cliente_id: int | None,
    tipo: str,
    data_previsao: str | None,
) -> list[str]:
    """Valida dados para criação de OS/Orçamento. Retorna lista de erros (vazia se OK)."""
    erros = []
    if not cliente_id:
        erros.append("Informe o cliente.")
    if tipo not in ("os", "orcamento"):
        erros.append("Tipo inválido.")
    if data_previsao:
        try:
            date.fromisoformat(data_previsao[:10])
        except ValueError:
            erros.append("Data de previsão inválida.")
    return erros


def validar_transicao_status(status_atual: str, status_novo: str) -> tuple[bool, str | None]:
    """Valida transição de status. Retorna (ok, mensagem_erro)."""
    if status_novo == "cancelado":
        if status_atual in ("entregue", "convertido"):
            return False, "Não é possível cancelar um registro entregue ou convertido."
        return True, None

    proximo = proximo_status(status_atual)
    if not proximo:
        return False, f"Status '{status_atual}' não permite avanço."

    if status_novo != proximo:
        return False, f"Transição inválida: {status_atual} → {status_novo}. Próximo: {proximo}."

    return True, None


def calcular_valor_total(itens: list[dict]) -> float:
    """Calcula valor total da OS/Orçamento a partir dos itens."""
    total = 0.0
    for item in itens:
        qtd = float(item.get("quantidade", 0) or 0)
        valor = float(item.get("valor_unitario", 0) or 0)
        desc = float(item.get("desconto", 0) or 0)
        total += (qtd * valor) - desc
    return round(total, 2)


# Mapeamento de forma_pagamento para rótulo
FORMA_PAGAMENTO_LABEL = dict(FORMAS_PAGAMENTO)

# Constantes para UI
STATUS_ORDEM = [s.value for s in StatusOs]
TIPOS_OS = [t.value for t in TipoOs]


# Mapeamento status -> cor/classe CSS para UI
STATUS_CLASSE = {
    "aberto": "primary",
    "aprovado": "info",
    "producao": "warning",
    "pronta": "success",
    "entregue": "success",
    "cancelado": "error",
    "convertido": "muted",
}

# Ordem dos status para ordenação
STATUS_ORDEM = {
    "aberto": 1,
    "aprovado": 2,
    "producao": 3,
    "pronta": 4,
    "entregue": 5,
    "cancelado": 6,
    "convertido": 7,
}


def status_badge_class(status: str) -> str:
    """Retorna classe CSS do badge para o status."""
    return STATUS_CLASSE.get(status, "muted")


def ordenar_por_status(os_list: list[dict]) -> list[dict]:
    """Ordena lista de OS/Orçamentos por status (ordem do fluxo) e depois por número."""
    return sorted(os_list, key=lambda o: (STATUS_ORDEM.get(o.get("status", ""), 99), -o.get("numero", 0)))


__all__ = [
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
    "STATUS_ORDEM",
    "STATUS_CLASSE",
    "STATUS_ORDEM",
    "TIPOS_OS",
    "status_badge_class",
    "ordenar_por_status",
]