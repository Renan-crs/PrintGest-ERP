"""Autenticação e sessão — login, bloqueio por tentativas, logout."""

import uuid

from tests.conftest import auth


def _login_unico(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_login_admin(client, admin_token):
    assert admin_token
    resp = client.get("/v1/auth/me", headers=auth(client, admin_token))
    assert resp.status_code == 200
    assert resp.json()["data"]["nivel_acesso"] == "admin"


def test_login_senha_errada(client):
    resp = client.post("/v1/auth/login", json={"login": "admin", "senha": "errada"})
    assert resp.status_code in (401, 423)


def test_sem_token_401(client):
    resp = client.get("/v1/clientes")
    assert resp.status_code == 401


def test_bloqueio_apos_5_falhas(client, admin_token):
    login = _login_unico("bloq")
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={"nome": "Teste Bloqueio", "login": login, "senha": "abc12345",
              "nivel_acesso": "operador"},
    )
    assert resp.status_code == 200, resp.text

    for _ in range(5):
        client.post("/v1/auth/login", json={"login": login, "senha": "errada"})

    resp = client.post("/v1/auth/login", json={"login": login, "senha": "abc12345"})
    assert resp.status_code == 423
    assert "bloqueado" in resp.json()["detail"].lower()


def test_logout_invalida_token(client, admin_token):
    resp = client.post("/v1/auth/logout", headers=auth(client, admin_token))
    assert resp.status_code == 200
    resp = client.get("/v1/auth/me", headers=auth(client, admin_token))
    assert resp.status_code == 401


def test_trocar_senha(client, admin_token):
    resp = client.post(
        "/v1/auth/trocar-senha",
        headers=auth(client, admin_token),
        json={"senha_atual": "admin123", "nova_senha": "novaSenha1"},
    )
    assert resp.status_code == 200, resp.text
    # volta senha para não quebrar demais fixtures/estado
    resp = client.post(
        "/v1/auth/trocar-senha",
        headers=auth(client, admin_token),
        json={"senha_atual": "novaSenha1", "nova_senha": "admin123"},
    )
    assert resp.status_code == 200, resp.text