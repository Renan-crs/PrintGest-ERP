"""Testes da tela de login e do fluxo de primeiro acesso.

Cobre o caso real do instalador: o administrador nasce sem senha, o login
responde 407 e a UI oferece a definição de senha. Também cobre o diálogo
isolado (validação local e envio para `/v1/auth/primeiro-acesso`).
"""

from __future__ import annotations

import json

import httpx
from PySide6.QtWidgets import QDialog

import printgest.ui.login as login_mod
from printgest.core.api import Api
from printgest.ui.login import LoginWindow, PrimeiroAcessoDialog

_SESSAO = {
    "token": "token-primeiro-acesso",
    "expira_em": "2026-11-03T12:00:00",
    "usuario": {"id": 1, "nome": "Administrador", "login": "admin", "nivel_acesso": "admin"},
}


def _api(handler) -> Api:
    return Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))


def _resposta(data, status=200):
    return httpx.Response(status, json={"data": data})


def _health_ok(request: httpx.Request) -> httpx.Response | None:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    return None


def test_login_407_abre_primeiro_acesso(app, monkeypatch):
    """407 do backend abre o diálogo de primeiro acesso e entra com a sessão."""
    abertos: list[dict] = []

    class DialogoFalso:
        def __init__(self, api, login="", parent=None):
            self.login = login
            self.sessao = dict(_SESSAO)
            abertos.append({"login": login, "api": api})

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(login_mod, "PrimeiroAcessoDialog", DialogoFalso)

    def handler(request: httpx.Request) -> httpx.Response:
        saudacao = _health_ok(request)
        if saudacao is not None:
            return saudacao
        assert request.url.path == "/v1/auth/login"
        return httpx.Response(
            407,
            json={
                "detail": "Este usuário está no primeiro acesso. Defina a senha."
            },
        )

    janela = LoginWindow(_api(handler))
    recebidas: list[dict] = []
    janela.autenticado.connect(recebidas.append)

    janela._campo_usuario.setText("admin")
    janela._campo_senha.setText("qualquer-coisa")
    janela._tentar_login()

    assert abertos and abertos[0]["login"] == "admin"
    assert recebidas == [_SESSAO]
    assert janela._botao_entrar.isEnabled() is True


def test_login_407_nao_entra_quando_dialogo_cancelado(app, monkeypatch):
    class DialogoFalso:
        def __init__(self, api, login="", parent=None):
            self.sessao = dict(_SESSAO)

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(login_mod, "PrimeiroAcessoDialog", DialogoFalso)

    def handler(request: httpx.Request) -> httpx.Response:
        saudacao = _health_ok(request)
        if saudacao is not None:
            return saudacao
        return httpx.Response(407, json={"detail": "primeiro acesso"})

    janela = LoginWindow(_api(handler))
    recebidas: list[dict] = []
    janela.autenticado.connect(recebidas.append)

    janela._campo_usuario.setText("admin")
    janela._campo_senha.setText("x")
    janela._tentar_login()

    assert recebidas == []
    assert janela._botao_entrar.isEnabled() is True


def test_login_senha_vazia_orienta_primeiro_acesso(app):
    """Sem senha não chama a API e explica onde definir a senha."""
    chamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return _resposta(True)

    janela = LoginWindow(_api(handler))
    janela._campo_usuario.setText("admin")
    janela._campo_senha.setText("")
    janela._tentar_login()

    assert "/v1/auth/login" not in chamadas
    assert "primeiro acesso" in janela._erro.text().lower()


def test_login_usuario_vazio_pede_usuario(app):
    def handler(request: httpx.Request) -> httpx.Response:
        return _resposta(True)

    janela = LoginWindow(_api(handler))
    janela._campo_usuario.setText("")
    janela._campo_senha.setText("qualquer")
    janela._tentar_login()

    assert janela._erro.text() == "Informe o usuário."


def test_primeiro_acesso_dialogo_valida_localmente(app):
    """Senha curta ou confirmação diferente não chegam ao backend."""
    chamadas: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return _resposta(_SESSAO)

    dialogo = PrimeiroAcessoDialog(_api(handler), login="admin")
    dialogo._campo_nova.setText("123")
    dialogo._campo_confirmar.setText("123")
    dialogo._definir()

    assert dialogo.sessao is None
    assert "8 caracteres" in dialogo._erro.text()

    dialogo._campo_nova.setText("senha12345")
    dialogo._campo_confirmar.setText("senha54321")
    dialogo._definir()

    assert dialogo.sessao is None
    assert "não conferem" in dialogo._erro.text()
    assert chamadas == []


def test_primeiro_acesso_dialogo_envia_nova_senha(app):
    """Sucesso devolve a sessão e fecha o diálogo."""
    recebidos: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/auth/primeiro-acesso"
        recebidos.append(json.loads(request.read().decode()))
        return _resposta(_SESSAO, status=201)

    dialogo = PrimeiroAcessoDialog(_api(handler), login="admin")
    dialogo._campo_nova.setText("senha12345")
    dialogo._campo_confirmar.setText("senha12345")
    dialogo._definir()

    assert recebidos == [{"login": "admin", "nova_senha": "senha12345"}]
    assert dialogo.sessao == _SESSAO
    assert dialogo.result() == QDialog.DialogCode.Accepted


def test_primeiro_acesso_dialogo_mostra_erro_do_backend(app):
    """Erro do backend (ex.: login já tem senha) aparece no diálogo."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"detail": "Login não encontrado ou já possui senha definida."}
        )

    dialogo = PrimeiroAcessoDialog(_api(handler), login="admin")
    dialogo._campo_nova.setText("senha12345")
    dialogo._campo_confirmar.setText("senha12345")
    dialogo._definir()

    assert dialogo.sessao is None
    assert "já possui senha" in dialogo._erro.text()
    assert dialogo._btn_definir.isEnabled() is True
