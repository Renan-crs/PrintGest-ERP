"""Execução silenciosa do daemon: logging sem stderr e specs de console.

A auditoria mostrou que o desktop já sobe o daemon com CREATE_NO_WINDOW;
o risco é o logging do uvicorn escrever em `sys.stderr=None`
caso o binário passe a ser windowed. Estes testes protegem o pré-requisito.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_specs_declaram_console_apenas_no_daemon():
    api = (RAIZ / "installer" / "printgestapi.spec").read_text(encoding="utf-8")
    desktop = (RAIZ / "installer" / "printgest.spec").read_text(encoding="utf-8")
    assert "console=True" in api
    assert "console=False" in desktop


def test_garantir_streams_substitui_stderr_none():
    import run_server

    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = None
        sys.stderr = None
        run_server._garantir_streams()
        assert sys.stdout is not None and sys.stderr is not None
        sys.stderr.write("ok\n")
    finally:
        sys.stdout, sys.stderr = original_stdout, original_stderr


def test_log_em_arquivo_precede_basic_config_e_nao_usa_stderr(
    monkeypatch, tmp_path
):
    import run_server

    root = logging.getLogger()
    handlers_originais = list(root.handlers)
    frozen = getattr(sys, "frozen", False)
    exe_original = sys.executable
    try:
        root.handlers = []
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "PrintGestAPI.exe"))
        run_server._anexar_log_em_arquivo()
        logging.basicConfig(level=logging.INFO)

        assert any(
            isinstance(h, logging.FileHandler) for h in root.handlers
        ), "FileHandler deve ser instalado antes do basicConfig"
        # FileHandler herda de StreamHandler; aqui queremos barrar apenas o
        # StreamHandler puro que o basicConfig(cria) apontando para stderr.
        assert not any(
            type(h) is logging.StreamHandler for h in root.handlers
        ), "basicConfig não deve criar StreamHandler para stderr inexistente"
        assert (tmp_path / "logs" / "printgest-api.log").exists()
    finally:
        root.handlers = handlers_originais
        monkeypatch.setattr(sys, "frozen", frozen, raising=False)
        monkeypatch.setattr(sys, "executable", exe_original)


def test_configurar_logging_sobrevive_a_stderr_none():
    from app.main import _configurar_logging

    root = logging.getLogger()
    handlers_originais = list(root.handlers)
    stderr_original = sys.stderr
    try:
        root.handlers = []
        sys.stderr = None
        _configurar_logging()  # não pode levantar AttributeError
        assert len(root.handlers) == 1
    finally:
        root.handlers = handlers_originais
        sys.stderr = stderr_original
