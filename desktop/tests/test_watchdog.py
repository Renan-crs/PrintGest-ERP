"""Watchdog do daemon e boot que não engole falhas."""

from __future__ import annotations

import printgest.ui.tela_principal as modulo
from printgest.ui.tela_principal import TelaPrincipal

_USUARIO = {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}


def _tela():
    return TelaPrincipal(api=object(), usuario=_USUARIO)


def test_watchdog_tenta_reanimar_daemon(app, monkeypatch):
    monkeypatch.setattr(modulo, "modo_estacao", lambda: False)
    garantias: list[dict] = []
    monkeypatch.setattr(
        "printgest.core.daemon.garantir",
        lambda **kwargs: garantias.append(kwargs) or True,
    )
    monkeypatch.setattr(
        modulo, "rodar", lambda fn, on_ok, on_erro: on_ok(fn())
    )

    tela = _tela()
    tela._daemon_offline("sem resposta")

    assert len(garantias) == 1
    assert garantias[0]["segundos"] == 30.0
    assert tela._watchdog_em_curso is False


def test_watchdog_em_estacao_nao_sobe_daemon(app, monkeypatch):
    monkeypatch.setattr(modulo, "modo_estacao", lambda: True)
    chamados: list = []
    monkeypatch.setattr(
        modulo, "rodar", lambda fn, on_ok, on_erro: chamados.append(fn)
    )
    tela = _tela()
    tela._daemon_offline("sem resposta")
    assert chamados == []


def test_watchdog_nao_inicia_segundo_ciclo(app, monkeypatch):
    monkeypatch.setattr(modulo, "modo_estacao", lambda: False)
    chamados: list = []
    monkeypatch.setattr(modulo, "rodar", lambda fn, on_ok, on_erro: chamados.append(fn))
    tela = _tela()
    tela._watchdog_em_curso = True
    tela._daemon_offline("sem resposta")
    assert chamados == []


def test_boot_com_falha_do_daemon_avisa_usuario(app, monkeypatch):
    import printgest.main as principal

    monkeypatch.setattr(principal.daemon, "saude", lambda *a, **k: False)
    monkeypatch.setattr(
        principal.daemon, "caminho_do_backend", lambda: "PrintGestAPI.exe"
    )
    monkeypatch.setattr(
        principal.daemon, "garantir", lambda *a, **k: False
    )
    avisos: list[str] = []
    monkeypatch.setattr(
        principal.QMessageBox, "warning", lambda *_a, **_k: avisos.append("daemon")
    )

    principal._preparar_daemon(app)

    assert avisos == ["daemon"]
