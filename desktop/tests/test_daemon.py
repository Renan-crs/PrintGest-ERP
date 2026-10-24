"""Testes do guardião do daemon (subida do Local API Service empacotado)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from printgest.core import daemon


def test_saude_indisponivel_canal_fechado(monkeypatch):
    monkeypatch.setattr(daemon, "SAUDE_URL", "http://127.0.0.1:1/health")
    assert daemon.saude() is False


def test_garantir_curto_circuito_quando_saudavel(monkeypatch):
    chamado = {"v": False}

    def saude_fake(timeout=1.0):
        chamado["v"] = True
        return True

    monkeypatch.setattr(daemon, "saude", saude_fake)
    assert daemon.garantir() is True
    assert chamado["v"] is True


def test_caminho_do_backend_por_variavel_de_ambiente(tmp_path, monkeypatch):
    exe = tmp_path / "PrintGestAPI.exe"
    exe.write_text("")
    monkeypatch.setenv("PRINTGEST_API_EXE", str(exe))
    assert daemon.caminho_do_backend() == exe

    monkeypatch.setenv("PRINTGEST_API_EXE", str(tmp_path / "sumiu.exe"))
    assert daemon.caminho_do_backend() is None


def test_caminho_do_backend_nao_empacotado_e_none(monkeypatch):
    import sys

    monkeypatch.delenv("PRINTGEST_API_EXE", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert daemon.caminho_do_backend() is None


def test_caminho_do_backend_congelado_acha_o_irmao(tmp_path, monkeypatch):
    import sys

    layout = tmp_path / "app"
    desktop_dir = layout / "PrintGest"
    api_dir = layout / "PrintGestAPI"
    desktop_dir.mkdir(parents=True)
    api_dir.mkdir(parents=True)
    (desktop_dir / "PrintGest.exe").write_text("")
    api = api_dir / "PrintGestAPI.exe"
    api.write_text("")

    monkeypatch.delenv("PRINTGEST_API_EXE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(desktop_dir / "PrintGest.exe"))
    assert daemon.caminho_do_backend() == api


def test_garantir_sobe_o_exe_e_espera_a_saude(monkeypatch, tmp_path):
    respostas = iter([False, False, True])
    monkeypatch.setattr(daemon, "saude", lambda timeout=1.0: next(respostas))
    exe = tmp_path / "PrintGestAPI" / "PrintGestAPI.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(daemon, "caminho_do_backend", lambda: exe)
    subidas: list[Path] = []
    monkeypatch.setattr(daemon, "subir", lambda c: subidas.append(c))

    assert daemon.garantir() is True
    assert subidas == [exe]


def test_garantir_sem_o_que_subir_devolve_false(monkeypatch):
    monkeypatch.setattr(daemon, "saude", lambda timeout=1.0: False)
    monkeypatch.setattr(daemon, "caminho_do_backend", lambda: None)
    assert daemon.garantir(segundos=0.1) is False


def test_subir_passa_cwd_e_flags_desanexados(monkeypatch, tmp_path):
    exe = tmp_path / "PrintGestAPI.exe"
    exe.write_text("")
    capturado: dict = {}

    class PopenFake:
        def __init__(self, *args, **kwargs):
            capturado.update(args=args, kwargs=kwargs)

    monkeypatch.setattr(daemon.subprocess, "Popen", PopenFake)
    daemon.subir(exe)
    assert capturado["args"] == ([str(exe)],)
    assert capturado["kwargs"]["cwd"] == str(exe.parent)
    assert capturado["kwargs"]["creationflags"] == (
        subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    )


def test_preparar_daemon_da_main_nao_abre_dialogo_quando_saudavel(
    app, monkeypatch
):
    from printgest import main as mod

    monkeypatch.setattr(mod.daemon, "saude", lambda: True)
    dialogos = []

    class SemDialogo:
        def __init__(self, *a, **k):
            dialogos.append(self)
            raise AssertionError("não deveria criar diálogo")

    monkeypatch.setattr("printgest.main.QProgressDialog", SemDialogo, raising=True)
    mod._preparar_daemon(app)
    assert dialogos == []
