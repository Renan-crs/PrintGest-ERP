"""Testes do roteador dev com licenciamento desabilitado (`PRINTGEST_LICENCA_DESABILITADA`)."""

from __future__ import annotations

import os

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
    # D3: a tela também faz o diagnóstico automático do servidor local.
    assert _REQUISICOES == ["/v1/licenca", "/health"]


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
    # O LoginWindow faz o diagnóstico do daemon (`/health`) ao abrir.
    assert [c for c in _REQUISICOES if c != "/health"] == ["/v1/licenca"]


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
    # Não consulta a licença; só o `/health` do diagnóstico do LoginWindow.
    assert all(c == "/health" for c in _REQUISICOES)


def test_modo_estacao_pula_o_serial_e_vai_ao_login(app):
    """D6/P5: estação não pede serial — a licença é do servidor da gráfica."""
    _REQUISICOES.clear()
    from printgest.main import _Roteador
    from printgest.ui.login import LoginWindow

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    roteador = _Roteador(api, estacao=True)

    roteador.iniciar()

    assert isinstance(roteador._janela, LoginWindow)
    # Nenhuma chamada de LICENÇA no modo Estação (o /health é do LoginWindow).
    assert all(c == "/health" for c in _REQUISICOES)


# ------------------------------------------------- .env da estação (P5)


def test_env_do_executavel_define_o_endereco(app, monkeypatch, tmp_path):
    """Instalador de estação grava o .env ao lado do exe (D6/P5)."""
    from printgest import main as mod

    monkeypatch.delenv("PRINTGEST_API_URL", raising=False)
    monkeypatch.delenv("PRINTGEST_MODO_ESTACAO", raising=False)
    ini = tmp_path / ".env"
    ini.write_text(
        "# Instalação de estação\n"
        "PRINTGEST_API_URL=192.168.0.10:8000\n"
        "PRINTGEST_MODO_ESTACAO=sim\n",
        encoding="utf-8",
    )

    mod._carregar_env_do_executavel(ini)

    assert os.environ["PRINTGEST_API_URL"] == "192.168.0.10:8000"
    assert os.environ["PRINTGEST_MODO_ESTACAO"] == "sim"


def test_env_do_executavel_nao_sobrescreve_variavel_real(app, monkeypatch, tmp_path):
    from printgest import main as mod

    monkeypatch.setenv("PRINTGEST_API_URL", "http://real:8000")
    ini = tmp_path / ".env"
    ini.write_text("PRINTGEST_API_URL=http://arquivo:8000\n", encoding="utf-8")

    mod._carregar_env_do_executavel(ini)

    assert os.environ["PRINTGEST_API_URL"] == "http://real:8000"


def test_env_do_executavel_tolerante(app, tmp_path):
    """Arquivo ausente, linhas inválidas e comentários não derrubam a app."""
    from printgest import main as mod

    mod._carregar_env_do_executavel(tmp_path / "inexistente.env")  # não explode
    ini = tmp_path / ".env"
    ini.write_text("sem igual\n=bloco\n# comentario=ignorado\n", encoding="utf-8")
    mod._carregar_env_do_executavel(ini)
    assert "sem igual" not in os.environ
    assert "comentario" not in os.environ


def test_janela_da_estacao_sobrevive_a_funcao_que_a_criou(app):
    """Regressão do GC: a ConexaoWindow precisa viver após `_iniciar_modo_estacao`.

    Referências locais (e `app.setProperty`, que não segura o wrapper Python)
    deixavam o objeto ser coletado — a janela C++ era destruída, o Qt via
    "última janela fechada" e o `exec()` saía com a tela piscando em branco.
    """
    from shiboken6 import Shiboken

    from printgest import main as mod

    mod._ESTACAO.clear()
    mod._iniciar_modo_estacao(app)

    janela = mod._ESTACAO["janela"]
    assert janela is not None
    assert janela.isVisibleTo(janela) or janela.isVisible()
    assert Shiboken.isValid(janela)  # objeto C++ vivo, não coletado