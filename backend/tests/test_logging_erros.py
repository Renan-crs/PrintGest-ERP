"""Todo erro deve ser detalhado no log, com traceback e sem segredos."""

from __future__ import annotations

import asyncio
import logging

from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from tests.conftest import auth


def _mensagens(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "printgest"]


def _request() -> Request:
    return Request({
        "type": "http", "method": "POST", "scheme": "http",
        "server": ("testserver", 80), "path": "/v1/teste",
        "query_string": b"", "headers": [],
    })


def test_404_e_detalhado_no_log(client, admin_token, caplog):
    caplog.set_level(logging.ERROR, logger="printgest")
    resp = client.get(
        "/v1/produtos/999999", headers=auth(client, admin_token)
    )
    assert resp.status_code == 404
    assert any(
        "HTTP 404" in m and "/v1/produtos/999999" in m and "detail=" in m
        for m in _mensagens(caplog)
    )


def test_422_e_detalhado_no_log(client, admin_token, caplog):
    caplog.set_level(logging.ERROR, logger="printgest")
    resp = client.post(
        "/v1/produtos", headers=auth(client, admin_token), json={}
    )
    assert resp.status_code == 422
    assert any("HTTP 422" in m and "RequestValidationError" in m
               for m in _mensagens(caplog))


def test_409_e_detalhado_no_log(client, admin_token, caplog):
    caplog.set_level(logging.ERROR, logger="printgest")
    h = auth(client, admin_token)
    primeira = client.post("/v1/financeiro/caixa/abrir", headers=h, json={})
    caixa_id = primeira.json()["data"]["id"]
    try:
        resp = client.post("/v1/financeiro/caixa/abrir", headers=h, json={})
        assert resp.status_code == 409
        assert any("HTTP 409" in m and "detail=" in m for m in _mensagens(caplog))
    finally:
        # Não deixar caixa aberto para os testes seguintes.
        client.post(
            f"/v1/financeiro/caixa/{caixa_id}/fechar", headers=h,
            json={"valor_informado": 0},
        )


def test_400_de_servico_e_logado(client, admin_token, caplog):
    caplog.set_level(logging.ERROR, logger="printgest")
    servico = client.post(
        "/v1/produtos", headers=auth(client, admin_token),
        json={"codigo": "SRVLOG", "nome": "Serviço", "tipo": "servico",
              "controla_estoque": False},
    ).json()["data"]
    resp = client.post(
        "/v1/produtos/variacoes/gerar",
        headers=auth(client, admin_token),
        json={"produto_pai_id": servico["id"],
              "variacoes": [{"tamanho": "M"}]},
    )
    assert resp.status_code == 400
    assert any("HTTP 400" in m and "detail=" in m for m in _mensagens(caplog))


def test_erro_nao_tratado_loga_traceback(caplog):
    from app.main import _erro_nao_tratado

    caplog.set_level(logging.ERROR, logger="printgest")
    try:
        raise RuntimeError("boom inesperado")
    except RuntimeError as exc:
        asyncio.run(_erro_nao_tratado(_request(), exc))
    texto = caplog.text
    assert "HTTP 500" in texto
    assert "RuntimeError" in texto and "boom inesperado" in texto


def test_segredos_sao_mascarados_no_log(caplog):
    from app.main import _erro_http

    caplog.set_level(logging.ERROR, logger="printgest")
    segredo = (
        "Bearer supersecreto postgresql://usuario:senha123@host/db "
        "token=abc123 1234-5678-9012-3456 sk_live_xyz"
    )
    exc = StarletteHTTPException(status_code=400, detail=segredo)
    asyncio.run(_erro_http(_request(), exc))

    texto = caplog.text
    for valor in (
        "supersecreto", "senha123", "abc123", "1234-5678-9012-3456",
        "sk_live_xyz",
    ):
        assert valor not in texto
    assert "***" in texto
