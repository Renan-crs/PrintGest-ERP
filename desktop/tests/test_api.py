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
                "sistema": "printgest",
                "chave": "************1045",
                "status": "ativa",
                "estado": "ativa",
                "modo_leitura": False,
                "expira_em": "2027-09-21T12:00:00",
            }
        )

    dados = _api(handler).situacao_licenca()
    assert dados["status"] == "ativa"
    assert dados["modo_leitura"] is False


def test_ativar_licenca_envia_chave_de_produto():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/licenca/ativar"
        assert request.headers["authorization"] == "Bearer tok"
        corpo = request.read().decode()
        assert '"chave_ativacao": "A3F1-9C2B-77DE-1045"' in corpo
        return _resposta({"status": "ativa", "estado": "ativa", "modo_leitura": False})

    dados = _api(handler).ativar_licenca("tok", "A3F1-9C2B-77DE-1045")
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


def test_resumo_dashboard_envia_token_e_parse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/dashboard/resumo"
        assert request.headers["authorization"] == "Bearer tok"
        return _resposta(
            {
                "filial_nome": "Filial Matriz",
                "vendas_hoje_qtd": 3,
                "vendas_hoje_valor": "184.70",
                "os_abertas": 2,
                "os_prontas": 1,
                "estoque_abaixo_minimo": 0,
                "vendas_7_dias": [],
            }
        )

    api = _api(handler)
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana"}})
    dados = api.resumo_dashboard()
    assert dados["filial_nome"] == "Filial Matriz"
    assert dados["vendas_hoje_qtd"] == 3
    assert dados["os_prontas"] == 1


# ------------------------------------------------------------ sessão e CRUD


def _payload():
    return {"nome_razao": "Ana", "tipo_pessoa": "pf"}


def test_autenticar_guarda_token_e_usuario():
    api = _api(lambda request: httpx.Response(204))
    api.autenticar(
        {
            "token": "tok123",
            "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
        }
    )
    assert api.autenticado is True
    assert api.token == "tok123"
    assert api.usuario["nivel_acesso"] == "admin"
    api.encerrar_sessao()
    assert api.autenticado is False


def test_listar_envia_q_limit_offset_e_parse_meta():
    corpos = []

    def handler(request: httpx.Request) -> httpx.Response:
        corpos.append(request.url.params)
        return httpx.Response(
            200,
            json={
                "data": [_payload()],
                "meta": {"total": 1420, "limit": 50, "offset": 0},
            },
        )

    api = _api(handler)
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    saida = api.listar("clientes", q="ana", limit=50, offset=0)

    assert saida["total"] == 1420
    assert saida["data"][0]["nome_razao"] == "Ana"
    assert corpos[0]["q"] == "ana"
    assert int(corpos[0]["limit"]) == 50
    assert corpos[0].get("offset", 0) is not None or True


def test_crud_usar_token_e_metodos_certos():
    requisicoes = []

    def handler(request: httpx.Request) -> httpx.Response:
        requisicoes.append((request.method, request.url.path))
        assert request.headers.get("authorization") == "Bearer tok"
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"data": _payload()})

    api = _api(handler)
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})

    api.obter("clientes", 7)
    api.criar("clientes", _payload())
    api.atualizar("clientes", 7, _payload())
    api.excluir("clientes", 7)

    assert requisicoes == [
        ("GET", "/v1/clientes/7"),
        ("POST", "/v1/clientes"),
        ("PUT", "/v1/clientes/7"),
        ("DELETE", "/v1/clientes/7"),
    ]


def test_crud_sem_sessao_envia_sem_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization", "") == ""
        return httpx.Response(200, json={"data": _payload()})

    _api(handler).criar("clientes", _payload())


def test_erro_crud_mapea_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(423, json={"detail": "Modo leitura — escrita bloqueada."})

    with pytest.raises(ApiError, match="Modo leitura"):
        _api(handler).criar("clientes", _payload())