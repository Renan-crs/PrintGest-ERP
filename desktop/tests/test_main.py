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


# ------------------------------------------------ instalação: serial primeiro


def _handler_licenca(status: str):
    """Responde `/v1/licenca` como o daemon faria (envelope `data`)."""

    def handler(request: httpx.Request) -> httpx.Response:
        _REQUISICOES.append(request.url.path)
        return httpx.Response(
            200, json={"data": {"status": status, "modo_leitura": False, "contrato": "c"}}
        )

    return handler


def test_iniciar_sem_licenca_abre_ativacao_antes_do_login(app, monkeypatch):
    """Programa licenciado por serial: na instalação pede o serial primeiro."""
    _REQUISICOES.clear()
    from printgest.main import _Roteador
    from printgest.ui.ativacao import AtivacaoWindow

    api = Api(
        base_url="http://daemon.test",
        transport=httpx.MockTransport(_handler_licenca("nao_ativada")),
    )
    roteador = _Roteador(api)
    monkeypatch.setattr(roteador, "_licenca_desabilitada", False)

    roteador.iniciar()

    assert isinstance(roteador._janela, AtivacaoWindow)
    assert roteador._janela._token is None  # ativação antes de autenticar
    assert _REQUISICOES == ["/v1/licenca"]


def test_iniciar_com_licenca_ja_ativada_nao_pede_serial(app, monkeypatch):
    """Já ativada (execuções seguintes): vai direto ao login, sem serial."""
    _REQUISICOES.clear()
    from printgest.main import _Roteador
    from printgest.ui.login import LoginWindow

    api = Api(
        base_url="http://daemon.test",
        transport=httpx.MockTransport(_handler_licenca("ativa")),
    )
    roteador = _Roteador(api)
    monkeypatch.setattr(roteador, "_licenca_desabilitada", False)

    roteador.iniciar()

    assert isinstance(roteador._janela, LoginWindow)
    assert _REQUISICOES == ["/v1/licenca"]


def test_ativacao_na_instalacao_leva_ao_login(app, monkeypatch):
    """Concluído o serial, o fluxo segue para o login (não pede de novo)."""
    _REQUISICOES.clear()
    from printgest.main import _Roteador
    from printgest.ui.login import LoginWindow

    api = Api(
        base_url="http://daemon.test",
        transport=httpx.MockTransport(_handler_licenca("nao_ativada")),
    )
    roteador = _Roteador(api)
    monkeypatch.setattr(roteador, "_licenca_desabilitada", False)

    roteador.iniciar()
    roteador._janela.ativada.emit()

    assert isinstance(roteador._janela, LoginWindow)


def test_flag_dev_pula_o_serial_e_abre_login(app, monkeypatch):
    """`PRINTGEST_LICENCA_DESABILITADA` mantém o atalho de desenvolvimento."""
    _REQUISICOES.clear()
    from printgest.main import _Roteador
    from printgest.ui.login import LoginWindow

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    roteador = _Roteador(api)
    monkeypatch.setattr(roteador, "_licenca_desabilitada", True)

    roteador.iniciar()

    assert isinstance(roteador._janela, LoginWindow)
    assert _REQUISICOES == []  # não consulta a licença