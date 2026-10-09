"""Endurecimento transversal — security headers, correlação e revogação de sessão.

Cobre os achados P13/P15/P20 aplicados no núcleo do serviço:
- headers de segurança e `X-Request-ID` em todas as respostas;
- reset de senha por admin encerra as sessões ativas do alvo.
"""

import uuid

from tests.conftest import auth


def _login_unico(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_security_headers_e_request_id(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert resp.headers.get("x-request-id")


def test_request_id_ecoado_quando_informado(client):
    resp = client.get("/health", headers={"X-Request-ID": "correlacao-123"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "correlacao-123"


def test_reset_senha_por_admin_revoga_sessoes(client, admin_token):
    login = _login_unico("rst")
    senha = "senhaInicial1"
    criado = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={"nome": "Reset Senha", "login": login, "senha": senha, "nivel_acesso": "operador"},
    )
    assert criado.status_code == 200, criado.text
    uid = criado.json()["data"]["id"]

    token = client.post(
        "/v1/auth/login", json={"login": login, "senha": senha}
    ).json()["data"]["token"]
    assert client.get("/v1/auth/me", headers=auth(client, token)).status_code == 200

    resp = client.put(
        f"/v1/usuarios/{uid}",
        headers=auth(client, admin_token),
        json={"senha": "senhaNova123"},
    )
    assert resp.status_code == 200, resp.text

    # A sessão antiga deixa de valer imediatamente.
    assert client.get("/v1/auth/me", headers=auth(client, token)).status_code == 401
    # E a senha nova passa a funcionar.
    novo = client.post("/v1/auth/login", json={"login": login, "senha": "senhaNova123"})
    assert novo.status_code == 200, novo.text
