"""Tela 1.2 — Ativação: validação de CNPJ por dígitos e comunicação honesta (P21).

Cobre o fluxo de ativação com `httpx.MockTransport` sem depender do daemon real:
- CNPJ com máscara é validado por contagem de dígitos (14), não por `len`;
- o botão "Testar Local API Service" reporta o estado verdadeiro do daemon.
"""

from __future__ import annotations

import httpx
from PySide6.QtWidgets import QPushButton

from printgest.core.api import Api
from printgest.ui.ativacao import AtivacaoWindow

_RESPOSTA_ATIVA = {"status": "ativa", "modo_leitura": False}


def _janela(handler) -> AtivacaoWindow:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    return AtivacaoWindow(api, token="tok")


def test_botao_de_comunicacao_e_honesto(app):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    textos = [b.text() for b in janela.findChildren(QPushButton)]
    assert any("Testar Local API Service" in t for t in textos)
    assert not any("RedGest respondendo" in t for t in textos)


def test_cnpj_incompleto_nao_chama_api(app):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    janela._campo_cnpj.setText("12.345.678/0001-9")  # 13 dígitos
    janela._campo_codigo.setText("PGST-ABCD-EFGH-IJKL-MNOP")
    janela._ativar()

    assert chamadas == []
    assert "14 dígitos" in janela._erro.text()


def test_cnpj_completo_ativa_e_emite_sinal(app, pumpar):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        assert request.headers["authorization"] == "Bearer tok"
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    emitiu = []
    janela.ativada.connect(lambda: emitiu.append(True))

    janela._campo_cnpj.setText("12.345.678/0001-90")  # 14 dígitos
    janela._campo_codigo.setText("PGST-ABCD-EFGH-IJKL-MNOP")
    janela._ativar()

    pumpar(lambda: emitiu == [True])
    assert "/v1/licenca/ativar" in chamadas
    assert "Licença ativada" in janela._erro.text()


def test_cnpj_completo_sem_codigo_nao_chama_api(app):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    janela._campo_cnpj.setText("12.345.678/0001-90")
    janela._campo_codigo.setText("PGST-X")
    janela._ativar()

    assert chamadas == []
    assert "código de licença" in janela._erro.text()


def test_testar_comunicacao_ok_atualiza_status(app, pumpar):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    janela._testar()
    pumpar(lambda: "Local API Service respondendo" in janela._status.text())
    assert "HTTP 200 OK" in janela._status.text()


def test_testar_comunicacao_falha_atualiza_status(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    janela = _janela(handler)
    janela._testar()
    pumpar(lambda: "Sem resposta do Local API Service" in janela._status.text())