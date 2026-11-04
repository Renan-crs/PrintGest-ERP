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


def test_primeiro_acesso_funcionario(client, admin_token):
    """Funcionário criado pelo admin define a própria senha no primeiro acesso."""
    login = _login_unico("prim")
    criado = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Primeiro Acesso", "login": login},
    )
    assert criado.status_code == 200, criado.text
    assert criado.json()["data"]["login"] == login

    # Sem senha definida o login é recusado com 407 (a UI abre o primeiro acesso).
    resp = client.post("/v1/auth/login", json={"login": login, "senha": "qualquer"})
    assert resp.status_code == 407

    # A senha nova segue a mesma regra do trocar-senha (mínimo de 8).
    resp = client.post(
        "/v1/auth/primeiro-acesso",
        json={"login": login, "nova_senha": "123"},
    )
    assert resp.status_code == 422

    resp = client.post(
        "/v1/auth/primeiro-acesso",
        json={"login": login, "nova_senha": "senha12345"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["data"]["token"]
    assert client.get("/v1/auth/me", headers=auth(client, token)).status_code == 200

    # O primeiro acesso é de uso único.
    resp = client.post(
        "/v1/auth/primeiro-acesso",
        json={"login": login, "nova_senha": "outra12345"},
    )
    assert resp.status_code == 401

    resp = client.post(
        "/v1/auth/login", json={"login": login, "senha": "senha12345"}
    )
    assert resp.status_code == 200, resp.text


def test_funcionario_login_duplicado_409(client, admin_token):
    login = _login_unico("dup")
    primeiro = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Titular", "login": login},
    )
    assert primeiro.status_code == 200, primeiro.text

    resp = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Outro", "login": login},
    )
    assert resp.status_code == 409
    assert "login" in resp.json()["detail"].lower()


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


def test_trocar_senha_invalida_outras_sessoes(client, admin_token):
    """Troca de senha encerra as demais sessões ativas, mantendo a atual (P16 §5)."""
    login = _login_unico("trc")
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={"nome": "Troca Senha", "login": login, "senha": "senha123",
              "nivel_acesso": "operador"},
    )
    assert resp.status_code == 200, resp.text

    sessao_a = client.post("/v1/auth/login", json={"login": login, "senha": "senha123"})
    sessao_b = client.post("/v1/auth/login", json={"login": login, "senha": "senha123"})
    assert sessao_a.status_code == 200 and sessao_b.status_code == 200
    token_a = sessao_a.json()["data"]["token"]
    token_b = sessao_b.json()["data"]["token"]

    resp = client.post(
        "/v1/auth/trocar-senha",
        headers=auth(client, token_a),
        json={"senha_atual": "senha123", "nova_senha": "novaSenha2"},
    )
    assert resp.status_code == 200, resp.text

    # sessão B (outra) foi encerrada; sessão A (que trocou) permanece válida
    resp_b = client.get("/v1/auth/me", headers=auth(client, token_b))
    assert resp_b.status_code == 401
    resp_a = client.get("/v1/auth/me", headers=auth(client, token_a))
    assert resp_a.status_code == 200

    # login com a nova senha funciona; com a antiga não
    resp_antiga = client.post("/v1/auth/login", json={"login": login, "senha": "senha123"})
    assert resp_antiga.status_code in (401, 423)
    resp_nova = client.post("/v1/auth/login", json={"login": login, "senha": "novaSenha2"})
    assert resp_nova.status_code == 200