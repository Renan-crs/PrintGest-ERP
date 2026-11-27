"""Erros do desktop devem ser detalhados em logs/printgest.log."""

from __future__ import annotations

import logging

import httpx

from printgest.core.api import Api, ApiError
from printgest.core.logging_app import configurar_logging


def test_mascara_chave_de_licenca_e_dsn():
    from printgest.core.logging_app import mascarar

    texto = mascarar(
        "chave_ativacao=ABCD-EFGH-IJKL-MNOP "
        "database_url=postgresql://printgest:segredo@neon.host/db "
        "chave_licenca=XXXX-YYYY-ZZZZ-WWWW sk_live_abc123 "
        # Chave solta (sem `chave=`) — só o padrão de produto a pega.
        "Licença informada pelo suporte: QWER-ASDF-ZXCV-POIU"
    )
    assert "ABCD-EFGH-IJKL-MNOP" not in texto
    assert "XXXX-YYYY-ZZZZ-WWWW" not in texto
    assert "QWER-ASDF-ZXCV-POIU" not in texto
    assert "postgresql://printgest:segredo" not in texto
    assert "sk_live_abc123" not in texto
    assert texto.count("***") >= 3


def test_configurar_logging_cria_arquivo_rotativo(tmp_path):
    destino = tmp_path / "logs" / "printgest.log"
    caminho = configurar_logging(destino)
    logging.getLogger("printgest.desktop").error("erro de teste Bearer secreto123")
    assert caminho.exists()
    texto = caminho.read_text(encoding="utf-8")
    assert "erro de teste" in texto
    assert "secreto123" not in texto


def test_worker_loga_tipo_mensagem_e_traceback(app, caplog):
    from printgest.core.tarefas import _Worker

    caplog.set_level(logging.ERROR, logger="printgest.desktop")
    worker = _Worker()
    recebido = []
    worker._resultado.connect(lambda pedido, resultado: recebido.append(resultado))

    def chamada():
        raise RuntimeError("boom no worker token=abc123")

    worker._executar(7, chamada)
    assert recebido and recebido[0][0] is False
    texto = caplog.text
    assert "RuntimeError" in texto and "boom no worker" in texto
    assert "abc123" not in texto
    assert "Traceback" in texto


def test_api_loga_status_e_detalhe_sanitizado(caplog):
    caplog.set_level(logging.ERROR, logger="printgest.desktop")

    def handler(request):
        return httpx.Response(400, json={"detail": "Bearer supersecreto"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1}})
    try:
        api.listar("produtos")
    except ApiError as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("ApiError esperado")

    texto = caplog.text
    assert "HTTP 400" in texto
    assert "supersecreto" not in texto
    assert "***" in texto


def test_excepthook_loga_traceback_sem_modal(app, monkeypatch, caplog):
    from PySide6.QtWidgets import QMessageBox

    from printgest.main import _erro_inesperado

    monkeypatch.setattr(QMessageBox, "critical", lambda *_a, **_k: None)
    caplog.set_level(logging.ERROR, logger="printgest.desktop")
    try:
        raise RuntimeError("falha de startup senha=xyz")
    except RuntimeError as exc:
        _erro_inesperado(type(exc), exc, exc.__traceback__)

    texto = caplog.text
    assert "Erro não tratado no desktop" in texto
    assert "RuntimeError" in texto and "Traceback" in texto
    assert "xyz" not in texto
