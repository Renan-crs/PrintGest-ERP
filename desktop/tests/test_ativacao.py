"""Tela 1.2 — Ativação: validação do formato da chave de produto (P21).

Cobre o fluxo de ativação com `httpx.MockTransport` sem depender do daemon real:
- a chave é aceita no formato XXXX-XXXX-XXXX-XXXX (4 blocos hexadecimais);
- a digitação normaliza minúsculas e insere os hífens sozinha;
- o botão "Testar Local API Service" reporta o estado verdadeiro do daemon.
"""

from __future__ import annotations

import json

import httpx
from PySide6.QtWidgets import QPushButton

from printgest.core.api import Api
from printgest.ui.ativacao import AtivacaoWindow

_RESPOSTA_ATIVA = {"status": "ativa", "modo_leitura": False}
_CHAVE = "A3F1-9C2B-77DE-1045"


def _janela(handler) -> AtivacaoWindow:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    return AtivacaoWindow(api, token="tok")


def test_botao_de_comunicacao_e_honesto(app):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    textos = [b.text() for b in janela.findChildren(QPushButton)]
    assert any("Testar Local API Service" in t for t in textos)
    assert not any("RedGest respondendo" in t for t in textos)


def test_digitacao_formata_a_chave(app):
    janela = _janela(lambda r: httpx.Response(200, json={"data": _RESPOSTA_ATIVA}))
    janela._campo_chave.setText("a3f19c2b77de1045")
    assert janela._campo_chave.text() == _CHAVE


def test_chave_incompleta_nao_chama_api(app):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    janela._campo_chave.setText("A3F1-9C2B")  # 8 caracteres: incompleta
    janela._ativar()

    assert chamadas == []
    assert "XXXX-XXXX-XXXX-XXXX" in janela._erro.text()


def test_chave_completa_ativa_e_emite_sinal(app, pumpar):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        assert request.headers["authorization"] == "Bearer tok"
        assert json.loads(request.read())["chave_ativacao"] == _CHAVE
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    emitiu = []
    janela.ativada.connect(lambda: emitiu.append(True))

    janela._campo_chave.setText(_CHAVE)
    janela._ativar()

    pumpar(lambda: emitiu == [True])
    assert "/v1/licenca/ativar" in chamadas
    assert "Licença ativada" in janela._erro.text()


def test_erro_do_servidor_e_exibido(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"detail": "Chave de ativação não reconhecida pelo servidor."}
        )

    janela = _janela(handler)
    janela._campo_chave.setText(_CHAVE)
    janela._ativar()

    pumpar(lambda: "não reconhecida" in janela._erro.text())


def test_erro_nao_trava_o_botao(app, pumpar):
    janela = _janela(lambda r: httpx.Response(400, json={"detail": "Chave inválida."}))
    janela._campo_chave.setText(_CHAVE)
    janela._ativar()
    pumpar(lambda: janela._erro.text() != "")
    assert janela._botao_ativar.isEnabled()


def test_testar_comunicacao_e_bem_sucedido(app, pumpar):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    janela._testar()
    pumpar(lambda: "respondendo" in janela._status.text())


def test_testar_comunicacao_sem_daemon(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("daemon fora do ar")

    janela = _janela(handler)
    janela._testar()
    pumpar(lambda: "Sem resposta" in janela._status.text())
