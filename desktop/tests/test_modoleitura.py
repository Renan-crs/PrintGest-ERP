"""Tela 1.3 — Modo Leitura: renovação e diagnóstico honesto (P21).

Cobre `_renovar` (sucesso e falha), `_verificar_rede` (ok e offline) e o
texto de suporte — sem depender do daemon real (`httpx.MockTransport`).
"""

from __future__ import annotations

import httpx

from printgest.core.api import Api
from printgest.ui.modoleitura import ModoLeituraWindow

_RESP = {"status": "ativa", "modo_leitura": False}


def _janela(handler) -> ModoLeituraWindow:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    return ModoLeituraWindow(api, token="tok")


def test_renovar_com_sucesso_emite_sinal(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/licenca/renovar"
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"data": _RESP})

    janela = _janela(handler)
    renovadas = []
    janela.renovada.connect(lambda: renovadas.append(True))
    janela._renovar()

    pumpar(lambda: renovadas == [True])
    assert "renovada" in janela._mensagem.text().lower()


def test_renovar_falha_mantem_modo_leitura(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(423, json={"detail": "Sistema em modo de leitura."})

    janela = _janela(handler)
    renovadas = []
    janela.renovada.connect(lambda: renovadas.append(True))
    janela._renovar()

    pumpar(lambda: "Não foi possível renovar" in janela._mensagem.text())
    assert renovadas == []
    assert "modo leitura" in janela._mensagem.text().lower()


def test_verificar_rede_ok_diagnostico(app, pumpar):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    janela._verificar_rede()
    pumpar(lambda: "Rede local OK" in janela._diag_texto.toPlainText())


def test_verificar_rede_offline_diagnostico(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    janela = _janela(handler)
    janela._verificar_rede()
    pumpar(lambda: "Falha ao contatar o daemon" in janela._diag_texto.toPlainText())


def test_suporte_canais_sem_numero_ficticio(app):
    janela = _janela(lambda r: httpx.Response(404))
    janela._suporte()
    texto = janela._mensagem.text()
    assert "Canais de atendimento RedGest" in texto
    assert "98765-4321" not in texto