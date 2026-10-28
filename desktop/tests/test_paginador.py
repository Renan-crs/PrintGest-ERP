"""Testes de paginação (mockup 2.1): widget Paginador + navegação real na página de cadastro.

Cobre o pedido de validação de "listagem, paginação":
- grade carrega a primeira página e o rodapé informa total/página;
- › busca offset=50 e a grade troca de conteúdo;
- ›| salta para a última página (parcial) e desabilita ›;
- |‹ volta para a primeira;
- widget isolado: estados de habilitado/desabilitado e sinal `mudou`.
"""

from __future__ import annotations

import httpx
import pytest

from printgest.core.api import Api
from printgest.ui.modulos.clientes import PaginaClientes
from printgest.ui.paginador import LOTE, Paginador

# 120 registros: 3 páginas de LOTE (50) - a última com 20
_REGISTROS = [
    {"id": i, "nome_razao": f"Cliente {i:03d}", "tipo_pessoa": "pf"} for i in range(1, 121)
]
_GETS: list[httpx.Request] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/clientes":
        _GETS.append(request)
        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", LOTE))
        return httpx.Response(
            200,
            json={
                "data": _REGISTROS[offset : offset + limit],
                "meta": {"total": len(_REGISTROS), "limit": limit, "offset": offset},
            },
        )
    return httpx.Response(404, json={"detail": "rota não esperada"})


@pytest.fixture
def pagina():
    _GETS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaClientes(api)


def _ultimo_offset() -> int:
    return int(_GETS[-1].url.params.get("offset", 0))


# ------------------------------------------------------------ página de grade


def test_primeira_pagina_carrega_50_de_120(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == LOTE)
    assert pagina._total == 120
    info = pagina._paginador._info.text()
    assert "de 120 registros" in info
    assert "Pág 1 de 3" in pagina._paginador._pagina.text()
    assert not pagina._paginador._anterior.isEnabled()
    assert not pagina._paginador._primeira.isEnabled()
    assert pagina._paginador._proxima.isEnabled()
    assert pagina._paginador._ultima.isEnabled()
    assert pagina._tabela.item(0, 2).text() == "Cliente 001"
    assert _ultimo_offset() == 0


def test_proxima_pagina_busca_offset_50_e_troca_linhas(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == LOTE)
    pagina._paginador._proxima.click()
    pumpar(lambda: "Pág 2 de 3" in pagina._paginador._pagina.text())
    assert _ultimo_offset() == LOTE
    assert pagina._tabela.rowCount() == LOTE
    assert pagina._tabela.item(0, 2).text() == "Cliente 051"
    assert pagina._paginador._anterior.isEnabled()
    assert pagina._paginador._proxima.isEnabled()


def test_ultima_pagina_parcial_e_desabilita_proxima(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == LOTE)
    pagina._paginador._ultima.click()
    pumpar(lambda: "Pág 3 de 3" in pagina._paginador._pagina.text())
    assert _ultimo_offset() == 2 * LOTE
    # última página é parcial: 120 - 100 = 20 linhas
    assert pagina._tabela.rowCount() == 20
    assert pagina._tabela.item(0, 2).text() == "Cliente 101"
    assert not pagina._paginador._proxima.isEnabled()
    assert not pagina._paginador._ultima.isEnabled()
    assert pagina._paginador._anterior.isEnabled()


def test_botao_primeira_volta_para_pagina_1(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == LOTE)
    pagina._paginador._proxima.click()
    pumpar(lambda: "Pág 2 de 3" in pagina._paginador._pagina.text())
    pagina._paginador._primeira.click()
    pumpar(lambda: "Pág 1 de 3" in pagina._paginador._pagina.text())
    assert _ultimo_offset() == 0
    assert pagina._tabela.item(0, 2).text() == "Cliente 001"


def test_anterior_da_primeira_pagina_nao_dispara(app, pumpar, pagina):
    pumpar(lambda: pagina._tabela.rowCount() == LOTE)
    total_gets = len(_GETS)
    pagina._paginador._anterior.click()  # desabilitado: não dispara clicked()
    import time

    time.sleep(0.05)
    assert len(_GETS) == total_gets
    assert "Pág 1 de 3" in pagina._paginador._pagina.text()


# ------------------------------------------------------------------- widget


def test_widget_atualizar_estado_dos_botoes(app):
    pag = Paginador()
    pag.atualizar(120, 0, LOTE)
    assert not pag._primeira.isEnabled() and not pag._anterior.isEnabled()
    assert pag._proxima.isEnabled() and pag._ultima.isEnabled()

    pag.atualizar(120, LOTE, LOTE)
    assert pag._primeira.isEnabled() and pag._anterior.isEnabled()
    assert pag._proxima.isEnabled() and pag._ultima.isEnabled()

    pag.atualizar(120, 2 * LOTE, LOTE)
    assert not pag._proxima.isEnabled() and not pag._ultima.isEnabled()

    pag.atualizar(0, 0, LOTE)
    assert "Pág 1 de 1" in pag._pagina.text()
    assert not any(
        (pag._primeira.isEnabled(), pag._anterior.isEnabled(), pag._proxima.isEnabled(), pag._ultima.isEnabled())
    )


def test_widget_sinal_mudou_emite_offset(app):
    pag = Paginador()
    recebidos: list[int] = []
    pag.mudou.connect(recebidos.append)
    pag.atualizar(120, 0, LOTE)
    pag._proxima.click()
    assert recebidos == [LOTE]
    pag.atualizar(120, LOTE, LOTE)
    pag._ultima.click()
    assert recebidos[-1] == 2 * LOTE
