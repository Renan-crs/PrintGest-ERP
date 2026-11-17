"""Cofre da URL de consolidação Neon por filial (PRD v3.3 §5.5).

Cada filial usa um **role próprio** no Neon com RLS por `filial_id`
(RF-SC-02). A URL de conexão contém a senha, por isso fica cifrada no mesmo
cofre DPAPI das integrações — nunca em `.env`, banco, log ou backup.

Chave: `sync:<filial_id>`.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core import cofre
from app.core.config import settings

_NOME_ARQUIVO = "sync.dat"
_PREFIXO = "sync:"


def caminho() -> Path:
    configurado = (settings.cofre_integracoes_arquivo or "").strip()
    if configurado:
        return Path(configurado).with_name("sync.dat")
    import os

    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if local:
        return Path(local) / "PrintGest" / _NOME_ARQUIVO
    return Path.home() / ".printgest" / _NOME_ARQUIVO


def ler() -> dict:
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
    provisorio = arquivo.with_suffix(arquivo.suffix + ".tmp")
    provisorio.write_text(
        cofre.proteger(json.dumps(dados, ensure_ascii=False, sort_keys=True)),
        encoding="utf-8",
    )
    provisorio.replace(arquivo)


def chave(filial_id: int) -> str:
    return f"{_PREFIXO}{filial_id}"


def url(filial_id: int) -> str:
    guardado = str(ler().get(chave(filial_id)) or "")
    return cofre.revelar(guardado)


def definir_url(filial_id: int, valor: str | None) -> None:
    dados = ler()
    ch = chave(filial_id)
    texto = (valor or "").strip()
    if texto:
        dados[ch] = cofre.proteger(texto)
    else:
        dados.pop(ch, None)
    guardar(dados)


def remover(filial_id: int) -> None:
    dados = ler()
    dados.pop(chave(filial_id), None)
    guardar(dados)


def limpar() -> None:
    try:
        caminho().unlink(missing_ok=True)
    except OSError:
        pass
