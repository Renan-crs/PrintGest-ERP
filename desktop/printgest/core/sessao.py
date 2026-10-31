"""Gerenciamento de sessão persistente do usuário.

Armazena o token de autenticação e dados do usuário localmente para
manter a sessão viva entre reinicializações do computador.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

SESSION_FILE = Path.home() / ".printgest" / "session.json"

# Sessão expira após 8 horas de inatividade (28800 segundos)
SESSION_TIMEOUT_SEGUNDOS = 8 * 60 * 60


def _garantir_diretorio() -> None:
    """Garante que o diretório de sessão existe."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)


def _hash_sessao(token: str, usuario: dict[str, Any]) -> str:
    """Gera hash para validar integridade da sessão."""
    dados = json.dumps({"token": token, "usuario": usuario}, sort_keys=True)
    return hashlib.sha256(dados.encode("utf-8")).hexdigest()[:16]


def salvar_sessao(token: str, usuario: dict[str, Any]) -> None:
    """Salva os dados de sessão localmente."""
    _garantir_diretorio()
    dados = {
        "token": token,
        "usuario": usuario,
        "timestamp": time.time(),
        "hash": _hash_sessao(token, usuario),
    }
    SESSION_FILE.write_text(json.dumps(dados), encoding="utf-8")


def carregar_sessao() -> dict[str, Any] | None:
    """Carrega os dados de sessão se existirem e forem válidos.
    
    Verifica:
    - Arquivo existe
    - JSON é válido
    - Hash de integridade confere
    - Sessão não expirou (timeout de 8 horas)
    """
    if not SESSION_FILE.exists():
        return None
    try:
        dados = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        
        # Verifica campos obrigatórios
        if "token" not in dados or "usuario" not in dados or "timestamp" not in dados:
            return None
        
        # Verifica timeout (sessão expira após 8 horas)
        if time.time() - dados.get("timestamp", 0) > SESSION_TIMEOUT_SEGUNDOS:
            limpar_sessao()
            return None
        
        # Verifica integridade do hash
        hash_esperado = _hash_sessao(dados["token"], dados["usuario"])
        if dados.get("hash") != hash_esperado:
            limpar_sessao()
            return None
            
        return dados
    except (json.JSONDecodeError, OSError):
        pass
    return None


def limpar_sessao() -> None:
    """Remove os dados de sessão local."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def sessao_existe() -> bool:
    """Verifica se há uma sessão salva válida."""
    return carregar_sessao() is not None