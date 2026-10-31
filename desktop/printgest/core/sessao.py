"""Gerenciamento de sessão persistente do usuário.

Armazena o token de autenticação e dados do usuário localmente para
manter a sessão viva entre reinicializações do computador.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SESSION_FILE = Path.home() / ".printgest" / "session.json"


def _garantir_diretorio() -> None:
    """Garante que o diretório de sessão existe."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)


def salvar_sessao(token: str, usuario: dict[str, Any]) -> None:
    """Salva os dados de sessão localmente."""
    _garantir_diretorio()
    dados = {
        "token": token,
        "usuario": usuario,
        "timestamp": __import__("time").time(),
    }
    SESSION_FILE.write_text(json.dumps(dados), encoding="utf-8")


def carregar_sessao() -> dict[str, Any] | None:
    """Carrega os dados de sessão se existirem."""
    if not SESSION_FILE.exists():
        return None
    try:
        dados = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        # Verifica se o token é válido (não expirou)
        if "token" in dados and "usuario" in dados:
            return dados
    except (json.JSONDecodeError, OSError):
        pass
    return None


def limpar_sessao() -> None:
    """Remove os dados de sessão local."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def sessao_existe() -> bool:
    """Verifica se há uma sessão salva."""
    return carregar_sessao() is not None