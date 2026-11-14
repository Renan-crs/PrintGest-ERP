"""Sessão persistente do usuário (auto-login do desktop).

Regra de produto: o usuário logado só repete o login quando **reinicia o
computador** ou clica em **Sair** — fechar/abrir o programa, inatividade ou
reinício do daemon NÃO pedem login novamente.

Implementação:

- O token + usuário ficam em ``~/.printgest/session.json`` (hash de integridade;
  a validade real é do servidor, que guarda só o SHA-256 do token).
- A cópia local é **ligada à inicialização do Windows**: gravamos o boot time no
  login; ao abrir, se o boot mudou, o computador foi reiniciado → login.
- NÃO há expiração por tempo no desktop (nem de inatividade): quem decide a
  validade é o servidor (`usuario_sessao`, TTL deslizante longo — ver
  `session_ttl_minutes` no backend). Um token recusado (401) limpa a sessão.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

SESSION_FILE = Path.home() / ".printgest" / "session.json"

# Tolerância na comparação do boot time (relógios e arredondamentos).
_TOLERANCIA_BOOT_SEGUNDOS = 5.0


def tempo_boot() -> float | None:
    """Epoch (segundos) da inicialização do sistema; `None` se não detectável.

    Windows: uptime via `GetTickCount64` (ms desde o boot) → boot = agora − uptime.
    POSIX: campo `btime` do `/proc/stat`. Sem os dois, devolve `None` e a
    verificação de reboot é pulada (comportamento tolerante).
    """
    try:
        if sys.platform == "win32":
            import ctypes

            uptime_ms = ctypes.windll.kernel32.GetTickCount64()  # type: ignore[attr-defined]
            return time.time() - uptime_ms / 1000.0
        for linha in Path("/proc/stat").read_text(encoding="ascii").splitlines():
            if linha.startswith("btime"):
                return float(linha.split()[1])
    except (OSError, ValueError, AttributeError):
        return None
    return None


def _garantir_diretorio() -> None:
    """Garante que o diretório de sessão existe."""
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)


def _hash_sessao(token: str, usuario: dict[str, Any]) -> str:
    """Hash de integridade da cópia local (não é criptografia)."""
    dados = json.dumps({"token": token, "usuario": usuario}, sort_keys=True)
    return hashlib.sha256(dados.encode("utf-8")).hexdigest()[:16]


def salvar_sessao(token: str, usuario: dict[str, Any]) -> None:
    """Salva os dados de sessão, atados ao boot atual do sistema."""
    _garantir_diretorio()
    dados = {
        "token": token,
        "usuario": usuario,
        "boot": tempo_boot(),
        "hash": _hash_sessao(token, usuario),
    }
    SESSION_FILE.write_text(json.dumps(dados), encoding="utf-8")


def carregar_sessao() -> dict[str, Any] | None:
    """Devolve a sessão salva, ou `None` (limpando o arquivo) quando inválida.

    Inválida quando: arquivo ausente/corrompido, hash divergente ou o sistema
    foi **reiniciado** desde o login (boot time diferente) — nesse caso o
    usuário refaz o login, como pede a regra de produto.
    """
    if not SESSION_FILE.exists():
        return None
    try:
        dados = json.loads(SESSION_FILE.read_text(encoding="utf-8"))

        if "token" not in dados or "usuario" not in dados:
            return None

        # Integridade da cópia local.
        hash_esperado = _hash_sessao(dados["token"], dados["usuario"])
        if dados.get("hash") != hash_esperado:
            limpar_sessao()
            return None

        # Computador reiniciado desde o login → nova sessão.
        boot_gravado = dados.get("boot")
        boot_atual = tempo_boot()
        if (
            boot_gravado is not None
            and boot_atual is not None
            and abs(boot_atual - float(boot_gravado)) > _TOLERANCIA_BOOT_SEGUNDOS
        ):
            limpar_sessao()
            return None

        return dados
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return None


def limpar_sessao() -> None:
    """Remove os dados de sessão local."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


def sessao_existe() -> bool:
    """Verifica se há uma sessão salva válida."""
    return carregar_sessao() is not None
