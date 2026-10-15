"""Cache em memória dos catálogos completos usados para preencher combos.

Cada tela (O.S., Venda Balcão, Produtos, grade de itens) recarregava a lista
inteira (`GET ...?limit=1000`) sempre que abria — várias requisições idênticas
por sessão. Aqui o resultado fica guardado por um TTL curto e é invalidado
explicitamente após salvar um registro (`PaginaCrud._salvo`).

O carregamento continua assíncrono (`rodar`): quando o valor está fresco na
cache, o callback de sucesso é chamado imediatamente (mesma thread da UI).
"""

from __future__ import annotations

import time
from typing import Callable

import printgest.core.tarefas as tarefas

_TTL_SEGUNDOS = 300.0

# chave -> (monotonic_timestamp, resposta)
_cache: dict[str, tuple[float, dict]] = {}


def carregar(
    chave: str,
    buscador: Callable[[], dict],
    on_ok: Callable[[dict], None],
    on_erro: Callable[[str], None] | None = None,
    ttl: float = _TTL_SEGUNDOS,
) -> None:
    """Entrega o catálogo a `on_ok`, servindo da cache enquanto estiver fresco.

    `buscador` só é executado quando não há valor válido em cache.
    """
    entrada = _cache.get(chave)
    if entrada is not None and (time.monotonic() - entrada[0]) < ttl:
        on_ok(entrada[1])
        return

    def _recebido(dados: dict) -> None:
        _cache[chave] = (time.monotonic(), dados)
        on_ok(dados)

    tarefas.rodar(buscador, on_ok=_recebido, on_erro=on_erro or (lambda _msg: None))


def invalidar(*chaves: str) -> None:
    """Remove as chaves informadas do cache (todas, se nenhuma for dada)."""
    if not chaves:
        _cache.clear()
        return
    for chave in chaves:
        _cache.pop(chave, None)


def limpar() -> None:
    """Esvazia o cache (usado nos testes para isolar o estado entre casos)."""
    _cache.clear()
