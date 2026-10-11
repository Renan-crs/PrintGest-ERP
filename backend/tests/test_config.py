"""Módulo Configuração (PRD §1.8 / telas_e_fluxos §1.8, §2.6).

Cobre Dados da Empresa / Personalização (atualização parcial da `empresa`) e o
Reajuste de Preços em Bloco (simulação, critérios, proteção de `bloqueado_reajuste`,
confirmação por senha e trilha de auditoria em `preco_reajuste_historico`).
"""

import uuid
from decimal import Decimal

from app.db import SessionLocal
from app.models.cadastros import Produto, ProdutoCategoria
from app.models.enums import NivelAcesso, TipoProduto
from tests.conftest import auth

FILIAL = 1


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _token_de(client, admin_token, nivel: str) -> str:
    login, senha = f"cfg{_u()}", "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={"nome": f"Usuário {nivel}", "login": login, "senha": senha, "nivel_acesso": nivel},
    )
    assert resp.status_code == 200, resp.text
    return client.post(
        "/v1/auth/login", json={"login": login, "senha": senha}
    ).json()["data"]["token"]


def _categoria() -> int:
    db = SessionLocal()
    try:
        cat = ProdutoCategoria(filial_id=FILIAL, nome=f"Categoria {_u()}")
        db.add(cat)
        db.commit()
        db.refresh(cat)
        return cat.id
    finally:
        db.close()


def _produto(preco: str = "100.00", *, categoria_id: int | None = None, bloqueado: bool = False) -> int:
    db = SessionLocal()
    try:
        produto = Produto(
            filial_id=FILIAL,
            categoria_id=categoria_id,
            codigo=f"P{_u()}"[:30],
            nome=f"Produto {_u()}",
            tipo=TipoProduto.PRODUTO,
            unidade="un",
            preco_custo=Decimal("10.00"),
            preco_venda=Decimal(preco),
            bloqueado_reajuste=bloqueado,
        )
        db.add(produto)
        db.commit()
        db.refresh(produto)
        return produto.id
    finally:
        db.close()


def _preco(produto_id: int) -> Decimal:
    db = SessionLocal()
    try:
        return Decimal(db.get(Produto, produto_id).preco_venda)
    finally:
        db.close()


# ------------------------------------------------------------ empresa / personalização
def test_empresa_get_e_update_parcial(client, admin_token):
    headers = auth(client, admin_token)
    lista = client.get("/v1/config/empresa", headers=headers)
    assert lista.status_code == 200, lista.text
    empresa = lista.json()["data"]
    assert empresa["razao_social"]

    # Atualização parcial (Personalização) não apaga o cadastro fiscal.
    fantasia = f"Fantasia {_u()}"
    resp = client.put(
        "/v1/config/empresa", headers=headers, json={"nome_fantasia": fantasia}
    )
    assert resp.status_code == 200, resp.text
    atual = resp.json()["data"]
    assert atual["nome_fantasia"] == fantasia
    assert atual["razao_social"] == empresa["razao_social"]

    logos = client.put(
        "/v1/config/empresa",
        headers=headers,
        json={
            "logotipo_path": "C:/printgest/logo.png",
            "fundo_tela_path": "C:/printgest/fundo.jpg",
            "impressora_matricial": "EPSON LX-300",
            "impressora_cupom": "Bematech MP-4200",
        },
    )
    assert logos.status_code == 200, logos.text
    dados = logos.json()["data"]
    assert dados["logotipo_path"] == "C:/printgest/logo.png"
    assert dados["nome_fantasia"] == fantasia  # segue intacto


def test_config_exige_admin(client, admin_token):
    gerente = auth(client, _token_de(client, admin_token, NivelAcesso.GERENTE.value))
    assert client.get("/v1/config/empresa", headers=gerente).status_code == 403

    operador = auth(client, _token_de(client, admin_token, NivelAcesso.OPERADOR.value))
    assert client.get("/v1/config/reajuste/historico", headers=operador).status_code == 403


# --------------------------------------------------------------------- reajuste
def test_simular_percentual_todos(client, admin_token):
    headers = auth(client, admin_token)
    produto_id = _produto("200.00")
    resp = client.post(
        "/v1/config/reajuste/simular",
        headers=headers,
        json={"criterio": "todos", "tipo_reajuste": "percentual", "valor": "10"},
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    item = next(i for i in dados["itens"] if i["produto_id"] == produto_id)
    assert Decimal(item["preco_antes"]) == Decimal("200.00")
    assert Decimal(item["preco_depois"]) == Decimal("220.00")
    assert dados["afetados"] >= 1


def test_simular_por_categoria_com_valor_fixo(client, admin_token):
    headers = auth(client, admin_token)
    alvo = _categoria()
    outra = _categoria()
    dentro = _produto("50.00", categoria_id=alvo)
    fora = _produto("80.00", categoria_id=outra)

    resp = client.post(
        "/v1/config/reajuste/simular",
        headers=headers,
        json={
            "criterio": "categoria",
            "categoria_id": alvo,
            "tipo_reajuste": "valor_fixo",
            "valor": "5",
        },
    )
    assert resp.status_code == 200, resp.text
    itens = resp.json()["data"]["itens"]
    ids = {i["produto_id"] for i in itens}
    assert dentro in ids
    assert fora not in ids
    item = next(i for i in itens if i["produto_id"] == dentro)
    assert Decimal(item["preco_depois"]) == Decimal("55.00")


def test_simular_categoria_sem_id_retorna_400(client, admin_token):
    headers = auth(client, admin_token)
    resp = client.post(
        "/v1/config/reajuste/simular",
        headers=headers,
        json={"criterio": "categoria", "tipo_reajuste": "percentual", "valor": "10"},
    )
    assert resp.status_code == 400


def test_simular_pula_produtos_bloqueados(client, admin_token):
    headers = auth(client, admin_token)
    cat = _categoria()
    livre = _produto("100.00", categoria_id=cat)
    travado = _produto("100.00", categoria_id=cat, bloqueado=True)

    resp = client.post(
        "/v1/config/reajuste/simular",
        headers=headers,
        json={
            "criterio": "categoria",
            "categoria_id": cat,
            "tipo_reajuste": "percentual",
            "valor": "10",
        },
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    ids = {i["produto_id"] for i in dados["itens"]}
    assert livre in ids
    assert travado not in ids
    assert dados["bloqueados"] >= 1


def test_aplicar_exige_senha_correta_e_grava_historico(client, admin_token):
    headers = auth(client, admin_token)
    cat = _categoria()
    produto_id = _produto("100.00", categoria_id=cat)
    base = {
        "criterio": "categoria",
        "categoria_id": cat,
        "tipo_reajuste": "percentual",
        "valor": "10",
    }

    errado = client.post(
        "/v1/config/reajuste/aplicar",
        headers=headers,
        json={**base, "senha": "senha-errada"},
    )
    assert errado.status_code == 400, errado.text
    assert _preco(produto_id) == Decimal("100.00")  # nada foi aplicado

    ok = client.post(
        "/v1/config/reajuste/aplicar",
        headers=headers,
        json={**base, "senha": "admin123"},
    )
    assert ok.status_code == 200, ok.text
    resultado = ok.json()["data"]
    assert resultado["afetados"] >= 1
    assert _preco(produto_id) == Decimal("110.00")

    historico = client.get("/v1/config/reajuste/historico", headers=headers).json()["data"]
    registro = next(h for h in historico if h["id"] == resultado["historico_id"])
    assert registro["tipo_reajuste"] == "percentual"
    assert registro["criterio"] == f"categoria:{cat}"
    assert registro["itens_afetados"] >= 1


def test_aplicar_sem_elegiveis_retorna_400(client, admin_token):
    headers = auth(client, admin_token)
    cat = _categoria()
    _produto("100.00", categoria_id=cat, bloqueado=True)
    resp = client.post(
        "/v1/config/reajuste/aplicar",
        headers=headers,
        json={
            "criterio": "categoria",
            "categoria_id": cat,
            "tipo_reajuste": "percentual",
            "valor": "10",
            "senha": "admin123",
        },
    )
    assert resp.status_code == 400, resp.text
