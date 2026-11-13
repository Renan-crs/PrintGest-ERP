"""Cópia de recuperação da ativação, fora do banco (sobrevive à reinstalação).

O cofre do SO (`app.core.cofre`) cifra o segredo **dentro da tabela `licenca`**:
se a instalação é refeita, o banco é recriado ou a linha se perde, as
credenciais M2M somem. O RedGest emite o `client_secret` **uma única vez**
(manual §7.2) e recusa um novo `/ativar/` para uma licença já ativada — então a
mesma máquina ficaria impedida de reutilizar a licença sem um reset de suporte.

Este módulo mantém uma cópia do material de ativação em um arquivo da máquina,
fora do banco:

- Windows: ``%LOCALAPPDATA%\\PrintGest\\licenca.dat``
- demais:  ``~/.printgest/licenca.dat``

O conteúdo é um JSON com ``cnpj``, ``codigo``, ``licenca_id``, ``client_id`` e
``client_secret``, cifrado com o mesmo DPAPI de escopo de máquina do cofre
(``dpapi:v1:...``). Como o arquivo não pertence ao diretório de instalação, ele
sobrevive a desinstalar/reinstalar o PrintGest na mesma conta de usuário.

O arquivo **nunca** é fonte de verdade: é só uma cópia de recuperação. Falhas de
I/O são registradas e ignoradas — ativar/validar continua funcionando sem ele.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from app.core import cofre
from app.core.config import settings

logger = logging.getLogger(__name__)

NOME_ARQUIVO = "licenca.dat"


def caminho() -> Path:
    """Arquivo do cofre local (respeita ``PRINTGEST_COFRE_LICENCA_ARQUIVO``)."""
    configurado = (settings.cofre_licenca_arquivo or "").strip()
    if configurado:
        return Path(configurado).expanduser()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / "PrintGest" / NOME_ARQUIVO
    return Path.home() / ".printgest" / NOME_ARQUIVO


def ler() -> dict:
    """Material de ativação guardado; ``{}`` quando não existe/está ilegível."""
    arquivo = caminho()
    try:
        bruto = arquivo.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        logger.warning(
            "Não foi possível ler o cofre local da licença (%s): %s", arquivo, exc
        )
        return {}
    texto = cofre.revelar(bruto.strip())
    if not texto:
        return {}
    try:
        dados = json.loads(texto)
    except ValueError:
        logger.warning("Cofre local da licença corrompido; ignorando o arquivo.")
        return {}
    return dados if isinstance(dados, dict) else {}


def guardar(dados: dict) -> None:
    """Grava o material de ativação de forma atômica (best-effort)."""
    arquivo = caminho()
    try:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        texto = cofre.proteger(
            json.dumps(dados, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
        temporario = arquivo.with_name(f"{arquivo.name}.tmp")
        temporario.write_text(texto, encoding="utf-8")
        os.replace(temporario, arquivo)
    except OSError as exc:
        logger.warning(
            "Não foi possível gravar o cofre local da licença (%s): %s", arquivo, exc
        )


def limpar() -> None:
    """Remove a cópia de recuperação (usado por testes e suporte)."""
    try:
        caminho().unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Não foi possível remover o cofre local da licença: %s", exc)


def salvar_tenant(cnpj: str) -> None:
    """Vincula a máquina ao inquilino (CNPJ) — base do instalador universal.

    A primeira ativação grava o CNPJ aqui; o daemon passa a resolver o
    inquilino pelo cofre local quando não há `PRINTGEST_EMPRESA_CNPJ` no `.env`.
    Best-effort: falha de I/O não impede a ativação (o CNPJ segue no banco).
    """
    dados = ler()
    dados["cnpj"] = "".join(c for c in cnpj if c.isdigit())
    guardar(dados)
