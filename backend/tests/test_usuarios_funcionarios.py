"""Auditoria de funcionários/usuários — correções de autenticação e permissões.

Cobre os achados A1, A2, A4, A5, A8 e A11 da auditoria de 24/11/2026.
"""

from __future__ import annotations

import uuid

from tests.conftest import auth


def _login_unico(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _criar_usuario(client, token: str, login: str, senha: str = "senha12345") -> dict:
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, token),
        json={
            "nome": f"Usuario {login}",
            "login": login,
            "senha": senha,
            "nivel_acesso": "operador",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _id_por_login(client, token: str, login: str) -> int:
    resp = client.get("/v1/usuarios", headers=auth(client, token), params={"q": login})
    assert resp.status_code == 200, resp.text
    itens = [u for u in resp.json()["data"] if u["login"] == login]
    assert itens, login
    return itens[0]["id"]


def _bloquear(client, login: str) -> None:
    """5 falhas → bloqueio de 30 min (settings.login_max_falhas)."""
    for _ in range(5):
        client.post("/v1/auth/login", json={"login": login, "senha": "errada"})


# --------------------------------------------------------------- A1


def test_login_recusa_usuario_inativo(client, admin_token):
    """Usuário desativado não consegue LOGAR (401), nem na primeira chamada."""
    login = _login_unico("inat")
    usuario = _criar_usuario(client, admin_token, login)
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "senha12345"}
    ).status_code == 200

    resp_desativar = client.put(
        f"/v1/usuarios/{usuario['id']}",
        headers=auth(client, admin_token),
        json={"ativo": False},
    )
    assert resp_desativar.status_code == 200, resp_desativar.text

    resp = client.post("/v1/auth/login", json={"login": login, "senha": "senha12345"})
    assert resp.status_code == 401
    # Mesma mensagem de credencial inválida: não confirma quais logins existem.
    assert "inválidos" in resp.json()["detail"].lower()


# --------------------------------------------------------------- A2


def test_bloqueio_vale_em_requisicao_autenticada(client, admin_token):
    """Sessão aberta é revogada na hora: bloqueio → 423 em /auth/me."""
    login = _login_unico("bloq2")
    _criar_usuario(client, admin_token, login)
    sessao = client.post("/v1/auth/login", json={"login": login, "senha": "senha12345"})
    assert sessao.status_code == 200, sessao.text
    token = sessao.json()["data"]["token"]
    assert client.get("/v1/auth/me", headers=auth(client, token)).status_code == 200

    _bloquear(client, login)

    resp = client.get("/v1/auth/me", headers=auth(client, token))
    assert resp.status_code == 423, resp.text
    assert "bloqueado" in resp.json()["detail"].lower()


# --------------------------------------------------------------- A4


def test_reset_senha_limpa_bloqueio(client, admin_token):
    """Reset por admin limpa falhas/bloqueio: usuário volta a logar na hora."""
    login = _login_unico("rst")
    usuario = _criar_usuario(client, admin_token, login)
    _bloquear(client, login)
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "senha12345"}
    ).status_code == 423

    resp = client.put(
        f"/v1/usuarios/{usuario['id']}",
        headers=auth(client, admin_token),
        json={"senha": "novaSenha123"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["falhas_login"] == 0
    assert resp.json()["data"]["bloqueado_em"] is None

    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "senha12345"}
    ).status_code == 401
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "novaSenha123"}
    ).status_code == 200


def test_reset_senha_limpa_primeiro_acesso(client, admin_token):
    """Reset por admin também resolve primeiro acesso pendente."""
    login = _login_unico("rstpa")
    criado = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Primeiro Acesso Reset", "login": login},
    )
    assert criado.status_code == 200, criado.text
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "qualquer123"}
    ).status_code == 407

    usuario_id = _id_por_login(client, admin_token, login)
    resp = client.put(
        f"/v1/usuarios/{usuario_id}",
        headers=auth(client, admin_token),
        json={"senha": "definida123"},
    )
    assert resp.status_code == 200, resp.text
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "definida123"}
    ).status_code == 200


def test_reset_da_propria_senha_nao_desloga_admin(client, admin_token):
    """Admin que redefine a própria senha preserva a sessão corrente."""
    eu = client.get("/v1/auth/me", headers=auth(client, admin_token)).json()["data"]

    resp = client.put(
        f"/v1/usuarios/{eu['id']}",
        headers=auth(client, admin_token),
        json={"senha": "temporaria123"},
    )
    assert resp.status_code == 200, resp.text
    assert client.get("/v1/auth/me", headers=auth(client, admin_token)).status_code == 200

    # Restaura a senha do admin para não contaminar os demais testes.
    resp = client.put(
        f"/v1/usuarios/{eu['id']}",
        headers=auth(client, admin_token),
        json={"senha": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    assert client.post(
        "/v1/auth/login", json={"login": "admin", "senha": "admin123"}
    ).status_code == 200


# --------------------------------------------------------------- A11


def test_admin_pode_desbloquear_usuario(client, admin_token):
    login = _login_unico("unlk")
    usuario = _criar_usuario(client, admin_token, login)
    _bloquear(client, login)

    resp = client.post(
        f"/v1/usuarios/{usuario['id']}/desbloquear",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["falhas_login"] == 0
    assert resp.json()["data"]["bloqueado_em"] is None
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "senha12345"}
    ).status_code == 200


# --------------------------------------------------------------- A5


def test_excluir_funcionario_desativa_usuario_e_revoga_sessao(client, admin_token):
    login = _login_unico("demit")
    criado = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Funcionario Demitido", "login": login},
    )
    assert criado.status_code == 200, criado.text
    funcionario_id = criado.json()["data"]["id"]
    usuario_id = _id_por_login(client, admin_token, login)

    primeiro = client.post(
        "/v1/auth/primeiro-acesso",
        json={"login": login, "nova_senha": "acesso12345"},
    )
    assert primeiro.status_code == 201, primeiro.text
    token = primeiro.json()["data"]["token"]
    assert client.get("/v1/auth/me", headers=auth(client, token)).status_code == 200

    resp = client.delete(
        f"/v1/funcionarios/{funcionario_id}", headers=auth(client, admin_token)
    )
    assert resp.status_code == 204, resp.text

    # Usuário vinculado desativado: token morto e login recusado (A1).
    assert client.get("/v1/auth/me", headers=auth(client, token)).status_code == 401
    assert client.post(
        "/v1/auth/login", json={"login": login, "senha": "acesso12345"}
    ).status_code == 401
    usuarios = client.get(
        "/v1/usuarios", headers=auth(client, admin_token), params={"q": login}
    ).json()["data"]
    assert usuarios[0]["id"] == usuario_id
    assert usuarios[0]["ativo"] is False


# --------------------------------------------------------------- A8


def test_put_funcionario_vazio_retorna_400(client, admin_token):
    login = _login_unico("vazio")
    criado = client.post(
        "/v1/funcionarios",
        headers=auth(client, admin_token),
        json={"nome": "Put Vazio", "login": login},
    )
    assert criado.status_code == 200, criado.text
    funcionario_id = criado.json()["data"]["id"]

    resp = client.put(
        f"/v1/funcionarios/{funcionario_id}",
        headers=auth(client, admin_token),
        json={},
    )
    assert resp.status_code == 400, resp.text
    assert "campo" in resp.json()["detail"].lower()

    # `login` é imutável: só ele no corpo também não há o que atualizar.
    resp = client.put(
        f"/v1/funcionarios/{funcionario_id}",
        headers=auth(client, admin_token),
        json={"login": _login_unico("novo")},
    )
    assert resp.status_code == 400

    # Corpo válido continua funcionando (regressão).
    resp = client.put(
        f"/v1/funcionarios/{funcionario_id}",
        headers=auth(client, admin_token),
        json={"cargo": "Atendente"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["cargo"] == "Atendente"
