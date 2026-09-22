"""Testes do cliente HTTP do desktop (`printgest.core.api`).

Usa `httpx.MockTransport` para não depender do daemon real.
"""

from __future__ import annotations

import httpx
import pytest

from printgest.core.api import Api, ApiError


def _api(handler) -> Api:
    transport = httpx.MockTransport(handler)
    return Api(base_url="http://daemon.test", transport=transport)


def _resposta(data, status=200):
    return httpx.Response(status, json={"data": data})


def test_login_envia_credenciais_e_retorna_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/auth/login"
        assert request.headers.get("authorization", "") == ""
        corpo = request.read().decode()
        assert '"login": "ana"' in corpo and '"senha": "1234"' in corpo
        return _resposta(
            {
                "token": "abc123",
                "expira_em": "2026-09-21T12:00:00",
                "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
            }
        )

    dados = _api(handler).login("ana", "1234")
    assert dados["token"] == "abc123"
    assert dados["usuario"]["login"] == "ana"


def test_situacao_licenca_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/licenca"
        return _resposta(
            {
                "sistema": "grafica_erp",
                "status": "ativa",
                "modo_leitura": False,
                "token_expira_em": "2026-09-21T12:00:00",
            }
        )

    dados = _api(handler).situacao_licenca()
    assert dados["status"] == "ativa"
    assert dados["modo_leitura"] is False


def test_ativar_licenca_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        corpo = request.read().decode()
        assert "12.345.678/0001-90" in corpo
        assert "PGST-ABCD-EFGH-IJKL-MNOP" in corpo
        assert request.headers["authorization"] == "Bearer tok"
        return _resposta({"status": "ativa", "modo_leitura": False})

    dados = _api(handler).ativar_licenca(
        "tok", "12.345.678/0001-90", "PGST-ABCD-EFGH-IJKL-MNOP"
    )
    assert dados["status"] == "ativa"


def test_renovar_licenca():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/licenca/renovar"
        assert request.headers["authorization"] == "Bearer tok"
        return _resposta({"status": "ativa", "modo_leitura": False})

    dados = _api(handler).renovar_licenca("tok")
    assert dados["status"] == "ativa"


def test_erro_mapea_detail_pt_br():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            423, json={"detail": "Sistema em modo leitura — escrite bloqueada."}
        )

    with pytest.raises(ApiError, match="modo leitura"):
        _api(handler).renovar_licenca("tok")


def test_testar_comunicacao_ok_e_offline():
    ok_api = _api(lambda request: httpx.Response(200, json={"status": "ok"}))
    assert ok_api.testar_comunicacao() is True

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    assert _api(offline).testar_comunicacao() is False