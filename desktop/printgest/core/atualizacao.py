"""Descoberta de nova versão via manifesto publicado na release do GitHub.

Fase 1 da análise de atualização: **apenas avisa**. Nenhum download, nenhuma
instalação, nenhuma alteração de sessão. Falha de rede, 404 ou manifesto
malformado são registrados no log e resultam em `None` — o sistema continua
funcionando exatamente como antes.

O manifesto `latest.json` é um asset da última release, então a URL é fixa e
não depende de autenticação nem da API local.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

URL_MANIFESTO = (
    "https://github.com/Renan-crs/PrintGest-ERP/releases/latest/download/latest.json"
)
_HOST_GITHUB = "github.com"
_VERSAO = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

logger = logging.getLogger("printgest.desktop")


def _tupla_versao(valor: str) -> tuple[int, int, int]:
    """Extrai `MAIOR.MENOR.PATCH`, ignorando prefixo `v` e sufixos."""
    match = _VERSAO.match(str(valor).strip())
    if not match:
        return (0, 0, 0)
    return tuple(int(parte) for parte in match.groups())


def versao_e_maior(atual: str, disponivel: str) -> bool:
    """True quando `disponivel` é uma versão mais nova que `atual`."""
    return _tupla_versao(disponivel) > _tupla_versao(atual)


def _manifesto_valido(dados: Any) -> bool:
    if not isinstance(dados, dict):
        return False
    if not _VERSAO.match(str(dados.get("versao", ""))):
        return False
    if not str(dados.get("arquivo", "")).lower().endswith(".exe"):
        return False
    if not _SHA256.match(str(dados.get("sha256", ""))):
        return False
    url = str(dados.get("url", ""))
    try:
        if httpx.URL(url).host.lower() != _HOST_GITHUB:
            return False
    except Exception:
        return False
    return True


def carregar_manifesto(cliente: httpx.Client | None = None) -> dict | None:
    """Busca e valida o manifesto; nunca levanta exceção para a UI."""
    pertence_ao_chamador = cliente is None
    cliente = cliente or httpx.Client(timeout=5.0, follow_redirects=True)
    try:
        resp = cliente.get(URL_MANIFESTO)
        if resp.status_code != 200:
            logger.info("Sem atualização: manifesto HTTP %s", resp.status_code)
            return None
        dados = resp.json()
        if not _manifesto_valido(dados):
            logger.warning("Manifesto de atualização inválido; ignorado.")
            return None
        return dados
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.info("Verificação de atualização indisponível: %s", type(exc).__name__)
        return None
    finally:
        if pertence_ao_chamador:
            cliente.close()


def verificar(
    versao_atual: str, cliente: httpx.Client | None = None
) -> dict | None:
    """Devolve dados para o banner somente se houver versão mais nova."""
    manifesto = carregar_manifesto(cliente)
    if manifesto is None:
        return None
    if not versao_e_maior(versao_atual, manifesto["versao"]):
        return None
    notas = manifesto.get("notas") or []
    if isinstance(notas, str):
        notas = [notas]
    return {
        "versao_nova": manifesto["versao"],
        "arquivo": manifesto["arquivo"],
        "sha256": manifesto["sha256"],
        "download_url": manifesto["url"],
        "revisoes": [str(n) for n in notas[:3]],
        "data": str(manifesto.get("data", "")),
    }
