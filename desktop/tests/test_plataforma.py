"""Telas de plataforma: envelope de filiais/estações e consolidação sem URL.

`PaginaEstacoes`/`PaginaFiliais` consumem o mesmo envelope `{"data": ...}` do
backend; `PaginaConsolidacao` deve mostrar estado amigável — não popup de erro —
quando o cofre não tem URL para a filial.
"""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from printgest.core.api import Api
from printgest.ui.modulos.plataforma import (
    PaginaConsolidacao,
    PaginaEstacoes,
    PaginaFiliais,
)

CONFIG = {"filial_id": 1, "configurado": False, "url_mascarada": None}


def _corpo(request: httpx.Request) -> dict:
    return json.loads(request.content or b"{}")


def _handler(request: httpx.Request) -> httpx.Response:
    path, metodo = request.url.path, request.method
    if path == "/v1/plataforma/estacoes" and metodo == "GET":
        return httpx.Response(
            200,
            json={
                "data": {
                    "total": 1,
                    "limite": 5,
                    "vagas": 4,
                    "estacoes": [
                        {
                            "id": 3,
                            "nome": "PC-01",
                            "fingerprint": "abc123def456",
                            "ultimo_acesso": "2026-11-27T10:00:00",
                            "dias_inativa": 0,
                        }
                    ],
                }
            },
        )
    if path == "/v1/plataforma/filiais" and metodo == "GET":
        return httpx.Response(
            200,
            json={
                "data": [{"id": 1, "nome": "Matriz", "papel": None, "ativa": True}],
                "meta": {"total": 1, "limit": 200, "offset": 0},
            },
        )
    if path == "/v1/plataforma/sync/config":
        if metodo == "GET":
            return httpx.Response(200, json={"data": dict(CONFIG)})
        url = _corpo(request).get("url")
        CONFIG["configurado"] = bool(url)
        CONFIG["url_mascarada"] = "***" + url[-8:] if url else None
        return httpx.Response(200, json={"data": dict(CONFIG)})
    if path in (
        "/v1/plataforma/consolidacao/relatorio",
        "/v1/plataforma/consolidacao/conflitos",
    ):
        if not CONFIG["configurado"]:
            return httpx.Response(
                503, json={"detail": "Consolidação não configurada para esta filial."}
            )
        return httpx.Response(200, json={"data": {"por_filial": [], "itens": []}})
    return httpx.Response(404, json={"detail": f"rota não esperada: {path}"})


def _api() -> Api:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return api


@pytest.fixture(autouse=True)
def _config_limpa():
    CONFIG.update({"configurado": False, "url_mascarada": None})


def test_estacoes_e_filiais_leem_envelope(app):
    estacoes = PaginaEstacoes(_api())
    assert estacoes._tabela.rowCount() == 1
    assert "1 de 5" in estacoes._lbl.text()

    filiais = PaginaFiliais(_api())
    assert filiais._tabela.rowCount() == 1


def test_consolidacao_sem_url_mostra_estado_sem_popup(app, monkeypatch):
    def falha(*_args, **_kwargs):
        raise AssertionError("popup de erro indevido ao abrir a aba")

    monkeypatch.setattr(QMessageBox, "warning", falha)
    pagina = PaginaConsolidacao(_api())
    assert "não configurada" in pagina._lbl_config.text()
    assert not pagina._btn_relatorio.isEnabled()
    assert not pagina._btn_descer.isEnabled()


def test_consolidacao_configura_url_no_cofre_e_habilita(app, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: None)
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_a, **_k: ("postgresql://usuario:senha@neon.host/db", True),
    )
    pagina = PaginaConsolidacao(_api())
    pagina._configurar()

    assert CONFIG["configurado"] is True
    assert CONFIG["url_mascarada"].startswith("***")
    assert "senha" not in CONFIG["url_mascarada"]
    assert "configurada" in pagina._lbl_config.text()
    assert pagina._btn_relatorio.isEnabled()

    pagina._btn_relatorio.click()
    assert "Atualizado em" in pagina._lbl_relatorio.text()


def test_consolidacao_erro_503_nao_vira_popup(app, monkeypatch):
    def falha(*_args, **_kwargs):
        raise AssertionError("503 de consolidação não deve virar popup")

    monkeypatch.setattr(QMessageBox, "warning", falha)
    pagina = PaginaConsolidacao(_api())
    pagina._erro_operacao("Consolidação não configurada para esta filial.", 503)
    assert "indisponível" in pagina._lbl_config.text().lower()

    # Outros status continuam com aviso ao operador.
    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: None)
    pagina._erro_operacao("falha de rede", 500)
