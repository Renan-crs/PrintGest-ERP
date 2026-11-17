"""Cofre das credenciais de integrações de terceiros (PRD v3.3 §3.6).

Segue o mesmo modelo de `cofre_maquina`: um arquivo JSON cifrado com DPAPI
(`cofre.proteger`), fora do banco, de logs e de backups. A chave de cada
credencial é `filial_id:integracao_id:campo` — isolamento por inquilino.

NUNCA devolva o valor em claro em resposta de API, log ou auditoria: use
`mascara()` para exibição.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.core import cofre
from app.core.config import settings

_NOME_ARQUIVO = "integracoes.dat"
_CHAVES = ("credencial", "certificado")


def caminho() -> Path:
    configurado = (settings.cofre_integracoes_arquivo or "").strip()
    if configurado:
        return Path(configurado).expanduser()
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local:
        return Path(local) / "PrintGest" / _NOME_ARQUIVO
    return Path.home() / ".printgest" / _NOME_ARQUIVO


def ler() -> dict:
    """Devolve o conteúdo decifrado (chave → valor em claro)."""
    arquivo = caminho()
    if not arquivo.exists():
        return {}
    try:
        texto = cofre.revelar(arquivo.read_text(encoding="utf-8"))
        dados = json.loads(texto or "{}")
    except (OSError, ValueError, TypeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def guardar(dados: dict) -> None:
    arquivo = caminho()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, sort_keys=True)
    provisorio = arquivo.with_suffix(arquivo.suffix + ".tmp")
    provisorio.write_text(cofre.proteger(texto), encoding="utf-8")
    os.replace(provisorio, arquivo)


def chave(filial_id: int, integracao_id: int | object, campo: str) -> str:
    return f"{filial_id}:{integracao_id}:{campo}"


def obter(filial_id: int, integracao_id: int | object, campo: str) -> str:
    if campo not in _CHAVES:
        raise ValueError(f"Campo de segredo desconhecido: {campo}")
    guardado = str(ler().get(chave(filial_id, integracao_id, campo)) or "")
    # Cada valor é cifrado individualmente ANTES de o JSON ser cifrado
    # (definir → guardar). Revelar o arquivo devolve o valor ainda cifrado.
    return cofre.revelar(guardado)


def definir(
    filial_id: int, integracao_id: int | object, campo: str, valor: str | None
) -> None:
    """Grava (ou remove, se vazio) uma credencial cifrada."""
    if campo not in _CHAVES:
        raise ValueError(f"Campo de segredo desconhecido: {campo}")
    dados = ler()
    ch = chave(filial_id, integracao_id, campo)
    texto = (valor or "").strip()
    if texto:
        dados[ch] = cofre.proteger(texto)
    else:
        dados.pop(ch, None)
    guardar(dados)


def remover_integracao(filial_id: int, integracao_id: int) -> None:
    """Apaga TODAS as credenciais de uma integração."""
    dados = ler()
    prefixo = f"{filial_id}:{integracao_id}:"
    for ch in [c for c in dados if str(c).startswith(prefixo)]:
        dados.pop(ch, None)
    guardar(dados)


def mascara(valor: str | None) -> str:
    """`***...1234` — nunca devolve o segredo completo."""
    texto = (valor or "").strip()
    if not texto:
        return ""
    visiveis = min(4, len(texto))
    return f"••••{texto[-visiveis:]}"


def limpar() -> None:
    """Testes: remove o arquivo do cofre."""
    try:
        caminho().unlink(missing_ok=True)
    except OSError:
        pass
