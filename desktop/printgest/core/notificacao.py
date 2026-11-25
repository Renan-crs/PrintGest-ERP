"""Helpers para mensagens exibidas ao usuário (A1/A2 da auditoria).

- `titulo_erro`: o backend devolve **423** tanto para licença em modo leitura
  quanto para usuário bloqueado por excesso de tentativas. O `detail` distingue
  os dois ("bloqueado" vs. mensagem de licença) — rotular tudo como
  "Modo leitura" induzia o operador a erro.
- `mensagem_segura`: aplica as mesmas máscaras do log antes de mostrar texto na
  UI (exceção crua, `ApiError`, `ultimo_erro` da licença).
"""

from __future__ import annotations

from printgest.core.logging_app import mascarar

TITULO_SESSAO = "Sessão encerrada"
TITULO_BLOQUEIO = "Usuário bloqueado"
TITULO_MODO_LEITURA = "Modo leitura"


def mensagem_segura(msg) -> str:
    """Texto seguro para QMessageBox/tooltips — nunca mostra segredos."""
    return mascarar(str(msg or ""))


def titulo_erro(
    status: int | None, msg="", titulo_padrao: str = "Não foi possível salvar"
) -> str:
    """Título coerente com o motivo do erro HTTP."""
    if status == 401:
        return TITULO_SESSAO
    if status == 423:
        if "bloqueado" in mensagem_segura(msg).lower():
            return TITULO_BLOQUEIO
        return TITULO_MODO_LEITURA
    return titulo_padrao
