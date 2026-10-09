"""Testes do roteador dev com licenciamento desabilitado (`PRINTGEST_LICENCA_DESABILITADA`)."""

from __future__ import annotations

import httpx

from printgest.core.api import Api
from printgest.ui.tela_principal import TelaPrincipal

_REQUISICOES: list[str] = []


def _handler(request: httpx.Request) -> httpx.Response:
    _REQUISICOES.append(request.url.path)
    return httpx.Response(404, json={"detail": "rota não esperada"})


def test_flag_env_parseia_booleanos(monkeypatch):
    from printgest import main as mod

    for ligado in ("true", "1", "yes", "on", "sim", "TRUE"):
        monkeypatch.setenv("PRINTGEST_LICENCA_DESABILITADA", ligado)
        assert mod._licenca_desabilitada() is True
    for desligado in ("false", "0", "no", "", "qualquer-coisa"):
        monkeypatch.setenv("PRINTGEST_LICENCA_DESABILITADA", desligado)
        assert mod._licenca_desabilitada() is False


def test_pos_login_sem_licenca_abre_dashboard_direto(app, monkeypatch):
    _REQUISICOES.clear()
    from printgest.main import _Roteador

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    roteador = _Roteador(api)
    monkeypatch.setattr(roteador, "_licenca_desabilitada", True)

    roteador._pos_login({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana"}})

    assert isinstance(roteador._janela, TelaPrincipal)
    assert api.autenticado is True
    assert _REQUISICOES == []  # sem chamada a /v1/licenca


def test_pos_login_com_licenca_ativa_consulta_licenca(app, pumpar, monkeypatch):
    _REQUISICOES.clear()
    from printgest.main import _Roteador

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    roteador = _Roteador(api)
    monkeypatch.setattr(roteador, "_licenca_desabilitada", False)
    monkeypatch.setattr(roteador, "_sem_daemon", lambda msg: None)

    roteador._pos_login({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana"}})

    pumpar(lambda: any(p == "/v1/licenca" for p in _REQUISICOES))