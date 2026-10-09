"""RBAC (PRD v2.0 §5) — acesso por nível nas rotas de cadastro e usuários."""

import uuid

from app.models.enums import NivelAcesso
from tests.conftest import auth


def _login() -> str:
    return f"lvl{uuid.uuid4().hex[:8]}"


def _criar_usuario(client, admin_token, nivel: NivelAcesso) -> tuple[str, str]:
    login, senha = _login(), "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={"nome": f"User {nivel.value}", "login": login, "senha": senha,
              "nivel_acesso": nivel.value},
    )
    assert resp.status_code == 200, resp.text
    return login, senha


def _login_usuario(client, login, senha):
    resp = client.post("/v1/auth/login", json={"login": login, "senha": senha})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def test_operador_pode_cadastros_nao_usuarios(client, admin_token):
    login, senha = _criar_usuario(client, admin_token, NivelAcesso.OPERADOR)
    token = _login_usuario(client, login, senha)

    resp = client.post("/v1/clientes", headers=auth(client, token),
                       json={"nome_razao": "Operador criou", "tipo_pessoa": "pf"})
    assert resp.status_code == 200, resp.text

    resp = client.post("/v1/produtos", headers=auth(client, token),
                       json={"codigo": f"OP{uuid.uuid4().hex[:6].upper()}", "nome": "Prod do Operador"})
    assert resp.status_code == 200, resp.text

    resp = client.get("/v1/usuarios", headers=auth(client, token))
    assert resp.status_code == 403

    resp = client.post("/v1/usuarios", headers=auth(client, token),
                       json={"nome": "não pode", "login": "x", "senha": "xxxx"})
    assert resp.status_code == 403


def test_caixa_sem_acesso_cadastros(client, admin_token):
    login, senha = _criar_usuario(client, admin_token, NivelAcesso.CAIXA)
    token = _login_usuario(client, login, senha)

    resp = client.get("/v1/clientes", headers=auth(client, token))
    assert resp.status_code == 403
    resp = client.post("/v1/funcionarios", headers=auth(client, token),
                       json={"nome": "não pode"})
    assert resp.status_code == 403


def test_gerente_sem_acesso_usuarios(client, admin_token):
    login, senha = _criar_usuario(client, admin_token, NivelAcesso.GERENTE)
    token = _login_usuario(client, login, senha)

    resp = client.get("/v1/usuarios", headers=auth(client, token))
    assert resp.status_code == 403
    # gerente tem cadastros
    resp = client.get("/v1/clientes", headers=auth(client, token))
    assert resp.status_code == 200


def test_admin_gerencia_usuarios(client, admin_token):
    resp = client.get("/v1/usuarios", headers=auth(client, admin_token))
    assert resp.status_code == 200
    logins = [u["login"] for u in resp.json()["data"]]
    assert "admin" in logins


def _id_admin(client, admin_token) -> int:
    resp = client.get("/v1/usuarios", headers=auth(client, admin_token))
    assert resp.status_code == 200
    return next(u["id"] for u in resp.json()["data"] if u["login"] == "admin")


def test_admin_nao_pode_desativar_a_si_mesmo(client, admin_token):
    """Guarda anti-lockout: admin não pode desativar o próprio usuário (P13/16)."""
    admin_id = _id_admin(client, admin_token)
    resp = client.put(
        f"/v1/usuarios/{admin_id}",
        headers=auth(client, admin_token),
        json={"ativo": False},
    )
    assert resp.status_code == 400
    assert "próprio" in resp.json()["detail"].lower()


def test_admin_nao_pode_rebaixar_a_si_mesmo(client, admin_token):
    """Guarda anti-lockout: admin não pode rebaixar o próprio nível (P13/16)."""
    admin_id = _id_admin(client, admin_token)
    resp = client.put(
        f"/v1/usuarios/{admin_id}",
        headers=auth(client, admin_token),
        json={"nivel_acesso": "caixa"},
    )
    assert resp.status_code == 400
    assert "rebaixar" in resp.json()["detail"].lower()


def test_admin_nao_pode_excluir_a_si_mesmo(client, admin_token):
    """Guarda anti-lockout: admin não pode excluir o próprio usuário (P13/16)."""
    admin_id = _id_admin(client, admin_token)
    resp = client.delete(f"/v1/usuarios/{admin_id}", headers=auth(client, admin_token))
    assert resp.status_code == 400
    assert "próprio" in resp.json()["detail"].lower()


def test_token_invalido_401(client):
    resp = client.get("/v1/clientes", headers=auth(client, "token-que-nao-existe"))
    assert resp.status_code == 401