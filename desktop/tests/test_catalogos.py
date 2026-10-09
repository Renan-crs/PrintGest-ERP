"""Testes do cache de catálogos (reduz requisições repetidas de combos)."""

from __future__ import annotations

from printgest.core import catalogos


def test_carregar_serve_da_cache_na_segunda_chamada(app, pumpar):
    chamadas: list[int] = []

    def buscador():
        chamadas.append(1)
        return {"data": []}

    recebidos: list[dict] = []
    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    pumpar(lambda: len(recebidos) == 1)  # 1ª vez: consulta de verdade

    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    # 2ª vez é servida da cache de forma síncrona — sem nova consulta.
    assert len(recebidos) == 2
    assert len(chamadas) == 1


def test_invalidar_forca_nova_consulta(app, pumpar):
    chamadas: list[int] = []

    def buscador():
        chamadas.append(1)
        return {"data": []}

    recebidos: list[dict] = []
    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    pumpar(lambda: len(recebidos) == 1)

    catalogos.invalidar("k")
    catalogos.carregar("k", buscador, on_ok=recebidos.append)
    pumpar(lambda: len(recebidos) == 2)
    assert len(chamadas) == 2
