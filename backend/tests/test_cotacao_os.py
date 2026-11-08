"""Item de fornecedor e cotações (M1 — PRD v3.0 §3.2.2/§3.2.3).

Cobre o fluxo: item terceirizado nasce "aguardando", cotações são lançadas por
Gerente/Admin, **uma** é selecionada (o item assume o VO e grava o snapshot),
os totais da OS são reprocessados — e a **confidencialidade**: Operador vê o
comparativo SEM `vf` e sem snapshot em nenhuma resposta (aceite §8.1).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import NivelAcesso
from tests.conftest import auth
from tests.test_rbac import _criar_usuario, _login_usuario


def _u() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _criar_cliente(client, token):
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, token),
        json={"nome_razao": f"Cliente Cot {_u()}", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_fornecedor(client, token, nome=None):
    resp = client.post(
        "/v1/fornecedores",
        headers=auth(client, token),
        json={"nome_razao": nome or f"Fornecedor {_u()}", "tipo_pessoa": "pj"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _criar_os_com_item_fornecedor(client, token, cliente, **extra):
    payload = {
        "tipo": "orcamento",
        "cliente_id": cliente["id"],
        "itens": [
            {
                "produto_id": None,
                "descricao_avulsa": "Hot stamping fosco 100x150mm",
                "quantidade": 1,
                "valor_unitario": 0,
                "tipo": "fornecedor",
            }
        ],
    }
    payload.update(extra)
    resp = client.post("/v1/os", headers=auth(client, token), json=payload)
    assert resp.status_code == 200, resp.text
    os_criada = resp.json()["data"]
    item = os_criada["itens"][0]
    assert item["tipo"] == "fornecedor"
    assert item["estado_cotacao"] == "aguardando"
    return os_criada, item


def _lancar(client, token, os_id, item_id, fornecedor_id, vf, **extra):
    corpo = {"fornecedor_id": fornecedor_id, "vf": vf}
    corpo.update(extra)
    return client.post(
        f"/v1/os/{os_id}/itens/{item_id}/cotacoes",
        headers=auth(client, token),
        json=corpo,
    )


# ------------------------------------------------------------------ fluxo M1


def test_cotacao_selecionada_calcula_vo_e_atualiza_a_os(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token, "Acabamentos SP")
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)

    resp = _lancar(
        client,
        admin_token,
        os_criada["id"],
        item["id"],
        fornecedor["id"],
        "100.00",
        selecionada=True,
        prazo_dias=5,
    )
    assert resp.status_code == 201, resp.text
    cotacao = resp.json()["data"]
    assert cotacao["selecionada"] is True
    assert Decimal(str(cotacao["vf"])) == Decimal("100.00")

    # O item assume o VO (PRD: só a selecionada compõe o orçamento)…
    resp = client.get(f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token))
    os_atual = resp.json()["data"]
    item_atual = os_atual["itens"][0]
    assert item_atual["estado_cotacao"] == "cotado"
    assert Decimal(str(item_atual["valor_unitario"])) == Decimal("243.80")
    # …e a OS reprocessa os totais (invariável itens − desconto).
    assert Decimal(str(os_atual["valor_itens"])) == Decimal("243.80")
    assert Decimal(str(os_atual["valor_total"])) == Decimal("243.80")

    # Snapshot no comparativo: o que foi aplicado fica registrado (§3.2.1).
    comp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, admin_token),
    ).json()
    assert comp["selecionado"] == {
        "vf": "100.00",
        "acrescimo_fornecedor_pct": "130",
        "markup_orcamento_pct": "6",
        "cp": "230.00",
        "vo": "243.80",
    }


def test_varias_cotacoes_e_somente_uma_selecionada(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    f1 = _criar_fornecedor(client, admin_token, "Laminadora A")
    f2 = _criar_fornecedor(client, admin_token, "Gráfica B")
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)

    primeira = _lancar(
        client,
        admin_token,
        os_criada["id"],
        item["id"],
        f1["id"],
        "100.00",
        selecionada=True,
    )
    assert primeira.status_code == 201
    segunda = _lancar(
        client, admin_token, os_criada["id"], item["id"], f2["id"], "87.35"
    )
    assert segunda.status_code == 201
    assert segunda.json()["data"]["selecionada"] is False

    # Trocar a seleção: só a segunda fica marcada e o VO passa a 212,96.
    resp = client.put(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/cotacoes/{segunda.json()['data']['id']}/selecionar",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text

    comp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, admin_token),
    ).json()
    marcadas = [c for c in comp["data"] if c["selecionada"]]
    assert len(marcadas) == 1
    assert Decimal(str(marcadas[0]["vf"])) == Decimal("87.35")
    assert comp["selecionado"]["cp"] == "200.91"
    assert comp["selecionado"]["vo"] == "212.96"

    os_atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert Decimal(str(os_atual["itens"][0]["valor_unitario"])) == Decimal("212.96")
    assert Decimal(str(os_atual["valor_total"])) == Decimal("212.96")


def test_cotacao_em_item_proprio_e_recusada(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    resp = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "orcamento",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "produto_id": None,
                    "descricao_avulsa": "Impressão interna",
                    "quantidade": 1,
                    "valor_unitario": "50.00",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    os_criada = resp.json()["data"]
    assert os_criada["itens"][0]["tipo"] == "proprio"
    assert os_criada["itens"][0]["estado_cotacao"] is None

    item_id = os_criada["itens"][0]["id"]
    resp = _lancar(
        client, admin_token, os_criada["id"], item_id, fornecedor["id"], "10.00"
    )
    assert resp.status_code == 409


# ------------------------------------------------------ confidencialidade §3.2.3


@pytest.fixture
def _tokens_por_nivel(client, admin_token):
    def criar(nivel: NivelAcesso) -> str:
        login, senha = _criar_usuario(client, admin_token, nivel)
        return _login_usuario(client, login, senha)

    return criar


def test_operador_ve_comparativo_sem_vf_nem_snapshot(
    client, admin_token, _tokens_por_nivel
):
    """Aceite §8.1: sem `ver_custo_terceiro`, nenhuma resposta contém VF/CP."""
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    _lancar(
        client,
        admin_token,
        os_criada["id"],
        item["id"],
        fornecedor["id"],
        "100.00",
        selecionada=True,
    )

    token_operador = _tokens_por_nivel(NivelAcesso.OPERADOR)
    resp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, token_operador),
    )
    assert resp.status_code == 200, resp.text
    corpo = resp.json()
    # OMITIDO, não oculto: a chave nem existe na resposta (§3.2.3).
    assert "vf" not in corpo["data"][0]
    assert corpo["selecionado"] is None
    assert "cp" not in str(corpo).lower().replace("lcp", "")

    # O item da OS segue sem custo: o VO é o valor do cliente, VF/CP não existem lá.
    os_operador = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, token_operador)
    ).json()["data"]
    assert "snapshot" not in str(os_operador).lower()


# ------------------------------------------ aprovação → pedido de compra (§3.2.2 item 7)


def test_converter_com_item_sem_cotacao_selecionada_e_bloqueado(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    _criar_fornecedor(client, admin_token, "Fornecedor X")
    os_criada, _item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    # nenhuma cotação lançada

    resp = client.post(
        f"/v1/os/{os_criada['id']}/converter", headers=auth(client, admin_token)
    )
    assert resp.status_code == 409, resp.text
    assert "sem cotação selecionada" in resp.json()["detail"]
    # o orçamento segue aberto
    atual = client.get(
        f"/v1/os/{os_criada['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert atual["status"] == "aberto"


def test_converter_gera_pedido_de_compra_rascunho_com_vf(client, admin_token):
    """Item 7: a aprovação gera pedido ABERTO por fornecedor com o VF cotado."""
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token, "Laminadora Prime")
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    resp = _lancar(
        client,
        admin_token,
        os_criada["id"],
        item["id"],
        fornecedor["id"],
        "87.35",
        selecionada=True,
        prazo_dias=7,
    )
    assert resp.status_code == 201

    resp = client.post(
        f"/v1/os/{os_criada['id']}/converter", headers=auth(client, admin_token)
    )
    assert resp.status_code == 200, resp.text
    os_nova = resp.json()["data"]
    assert os_nova["tipo"] == "os"
    # item copiado mantém tipo/snapshot
    assert os_nova["itens"][0]["tipo"] == "fornecedor"
    assert os_nova["itens"][0]["estado_cotacao"] == "cotado"
    assert Decimal(str(os_nova["itens"][0]["valor_unitario"])) == Decimal("212.96")

    # O pedido de compra em rascunho existe, com o VF (87,35 — valor interno).
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from tests.conftest import TEST_DB_URL

    engine = create_engine(TEST_DB_URL)
    with Session(engine) as db:
        pedidos = db.execute(
            text(
                "SELECT id, fornecedor_id, status, valor_total, os_origem_id "
                "FROM pedido_compra WHERE os_origem_id = :os"
            ),
            {"os": os_nova["id"]},
        ).fetchall()
        assert len(pedidos) == 1
        pedido = pedidos[0]
        assert pedido.fornecedor_id == fornecedor["id"]
        assert pedido.status == "aberto"
        assert Decimal(str(pedido.valor_total)) == Decimal("87.35")

        itens = db.execute(
            text(
                "SELECT pc.produto_id, pc.descricao_avulsa, pc.valor_unitario, "
                "       c.vf AS vf_cotacao, c.pedido_item_id "
                "FROM pedido_compra_item pc "
                "JOIN os_item_cotacao c ON c.pedido_item_id = pc.id "
                "WHERE pc.pedido_compra_id = :pid"
            ),
            {"pid": pedido.id},
        ).fetchall()
        assert len(itens) == 1
        assert itens[0].produto_id is None  # serviço: sem produto
        assert Decimal(str(itens[0].valor_unitario)) == Decimal("87.35")
        assert Decimal(str(itens[0].vf_cotacao)) == Decimal("87.35")
        assert "Hot stamping" in itens[0].descricao_avulsa
    engine.dispose()


def test_converter_agrupa_um_pedido_por_fornecedor(client, admin_token):
    """Dois itens para o MESMO fornecedor: um pedido, dois itens (§3.7)."""
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token, "Fornecedora Única")
    resp = client.post(
        "/v1/os",
        headers=auth(client, admin_token),
        json={
            "tipo": "orcamento",
            "cliente_id": cliente["id"],
            "itens": [
                {
                    "produto_id": None,
                    "descricao_avulsa": "Hot stamping fosco",
                    "quantidade": 1,
                    "valor_unitario": 0,
                    "tipo": "fornecedor",
                },
                {
                    "produto_id": None,
                    "descricao_avulsa": "Corte e vinco especial",
                    "quantidade": 1,
                    "valor_unitario": 0,
                    "tipo": "fornecedor",
                },
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    os_criada = resp.json()["data"]
    for item in os_criada["itens"]:
        r = _lancar(
            client,
            admin_token,
            os_criada["id"],
            item["id"],
            fornecedor["id"],
            "50.00",
            selecionada=True,
        )
        assert r.status_code == 201

    resp = client.post(
        f"/v1/os/{os_criada['id']}/converter", headers=auth(client, admin_token)
    )
    assert resp.status_code == 200, resp.text
    os_nova = resp.json()["data"]

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from tests.conftest import TEST_DB_URL

    engine = create_engine(TEST_DB_URL)
    with Session(engine) as db:
        pedidos = db.execute(
            text("SELECT id, valor_total FROM pedido_compra WHERE os_origem_id = :os"),
            {"os": os_nova["id"]},
        ).fetchall()
        assert len(pedidos) == 1  # um pedido por fornecedor
        assert Decimal(str(pedidos[0].valor_total)) == Decimal("100.00")  # 2 × VF 50
        itens = db.execute(
            text(
                "SELECT count(*) FROM pedido_compra_item WHERE pedido_compra_id = :pid"
            ),
            {"pid": pedidos[0].id},
        ).scalar_one()
        assert itens == 2
    engine.dispose()


def test_operador_e_caixa_nao_lancam_nem_selecionam(
    client, admin_token, _tokens_por_nivel
):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_criada, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)

    token_operador = _tokens_por_nivel(NivelAcesso.OPERADOR)
    resp = _lancar(
        client, token_operador, os_criada["id"], item["id"], fornecedor["id"], "10.00"
    )
    assert resp.status_code == 403

    # Caixa nem no router de OS entra (nível mínimo OPERADOR).
    token_caixa = _tokens_por_nivel(NivelAcesso.CAIXA)
    resp = client.get(
        f"/v1/os/{os_criada['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, token_caixa),
    )
    assert resp.status_code == 403
