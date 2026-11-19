"""Verificação API ↔ endpoints do PDV: catálogos legíveis por CAIXA.

O PDV roda com CAIXA (rank 1), mas os routers de cadastro exigem OPERADOR e o
de usuários exige ADMIN. Sem um espelho de leitura, os combos do PDV ficavam
vazios (403 silencioso) e o catálogo era cortado em 200 produtos.
"""

import uuid

from app.models.cadastros import Produto
from app.models.enums import NivelAcesso
from tests.conftest import auth


def _criar_caixa(client, admin_token):
    login = f"pdv{uuid.uuid4().hex[:8]}"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={
            "nome": "Caixa PDV",
            "login": login,
            "senha": "senha123",
            "nivel_acesso": NivelAcesso.CAIXA.value,
        },
    )
    assert resp.status_code == 200, resp.text
    login_resp = client.post("/v1/auth/login", json={"login": login, "senha": "senha123"})
    assert login_resp.status_code == 200, login_resp.text
    return auth(client, login_resp.json()["data"]["token"])


def test_caixa_le_catalogos_pdv(client, admin_token):
    h = _criar_caixa(client, admin_token)
    for caminho in (
        "/v1/pdv/clientes",
        "/v1/pdv/produtos",
        "/v1/pdv/funcionarios",
        "/v1/pdv/operadores",
    ):
        r = client.get(caminho, headers=h)
        assert r.status_code == 200, (caminho, r.text)
        assert "data" in r.json()

    # Operadores são uma projeção mínima: sem nível/email/tentativas de login.
    op = client.get("/v1/pdv/operadores", headers=h).json()["data"][0]
    assert set(op) == {"id", "nome", "login"}
    assert "nivel_acesso" not in op


def test_pdv_e_somente_leitura(client, admin_token):
    h = _criar_caixa(client, admin_token)
    assert client.post("/v1/pdv/clientes", headers=h, json={}).status_code == 405
    # Não existe rota de exclusão no espelho (404) e a de escrita é 405.
    assert client.delete("/v1/pdv/produtos/1", headers=h).status_code in (404, 405)


def test_caixa_continua_sem_cadastros_e_usuarios(client, admin_token):
    """O espelho de leitura NÃO afrouxa o RBAC das rotas originais."""
    h = _criar_caixa(client, admin_token)
    assert client.get("/v1/clientes", headers=h).status_code == 403
    assert client.get("/v1/usuarios", headers=h).status_code == 403
    assert client.get("/v1/produtos", headers=h).status_code == 403


def test_catalogo_pdv_devolve_mais_de_200(client, admin_token):
    from app.db import SessionLocal

    db = SessionLocal()
    sufixo = uuid.uuid4().hex[:6].upper()
    try:
        db.add_all(
            Produto(
                filial_id=1,
                codigo=f"PDV{sufixo}{i:03d}",
                nome=f"Produto {sufixo} {i}",
                preco_venda=1,
                ativo=True,
            )
            for i in range(205)
        )
        db.commit()
    finally:
        db.close()

    h = _criar_caixa(client, admin_token)
    r = client.get("/v1/pdv/produtos", headers=h, params={"limit": 1000})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["data"]) > 200
    assert corpo["meta"]["limit"] == 1000


def test_caixa_busca_sku_pelo_espelho_pdv(client, admin_token):
    sku = f"SKU-PDV-{uuid.uuid4().hex[:8]}"
    criacao = client.post(
        "/v1/produtos",
        headers=auth(client, admin_token),
        json={"codigo": sku, "sku": sku, "nome": "Variante PDV", "preco_venda": "10.00"},
    )
    assert criacao.status_code == 200, criacao.text

    h = _criar_caixa(client, admin_token)
    r = client.get(f"/v1/pdv/produtos/buscar-sku/{sku}", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["sku"] == sku
