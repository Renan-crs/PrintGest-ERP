"""Persistência do Orçamento — PUT não pode destruir cotação/snapshot.

Regressão: a UI reenvia a lista inteira de itens no PUT. Como `OsItemIn` não
tinha `id` e o service substituía a coleção, `delete-orphan` apagava cotações e
`snapshot_preco`; a conversão em O.S. falhava depois com 409.
"""

from decimal import Decimal

from tests.conftest import auth
from tests.test_cotacao_os import (
    _criar_cliente,
    _criar_fornecedor,
    _criar_os_com_item_fornecedor,
    _lancar,
    _u,
)


def _put_orcamento(client, token, os_id, cliente_id, itens, **extra):
    corpo = {
        "tipo": "orcamento",
        "cliente_id": cliente_id,
        "observacoes": f"editado {_u()}",
        "itens": itens,
    }
    corpo.update(extra)
    return client.put(f"/v1/os/{os_id}", headers=auth(client, token), json=corpo)


def test_put_preserva_cotacao_snapshot_e_conversao(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    orc, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)

    lancamento = _lancar(
        client, admin_token, orc["id"], item["id"], fornecedor["id"],
        "100.00", selecionada=True, prazo_dias=5,
    )
    assert lancamento.status_code == 201, lancamento.text

    antes = client.get(f"/v1/os/{orc['id']}", headers=auth(client, admin_token)).json()["data"]
    item_antes = antes["itens"][0]
    assert item_antes["estado_cotacao"] == "cotado"
    assert Decimal(str(item_antes["valor_unitario"])) == Decimal("243.80")

    # UI reenvia TODOS os itens; altera só a quantidade (mantém o `id`).
    item_editado = dict(item_antes)
    item_editado["quantidade"] = "2"
    resp = _put_orcamento(
        client, admin_token, orc["id"], cliente["id"], [item_editado]
    )
    assert resp.status_code == 200, resp.text

    depois = client.get(f"/v1/os/{orc['id']}", headers=auth(client, admin_token)).json()["data"]
    item_depois = depois["itens"][0]
    assert item_depois["id"] == item_antes["id"]
    assert item_depois["estado_cotacao"] == "cotado"
    assert Decimal(str(item_depois["valor_unitario"])) == Decimal("243.80")
    assert Decimal(str(item_depois["quantidade"])) == Decimal("2.000")
    assert Decimal(str(depois["valor_itens"])) == Decimal("487.60")

    # Snapshot e rastreio de terceirizado continuam intactos.
    comp = client.get(
        f"/v1/os/{orc['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, admin_token),
    ).json()
    assert comp["selecionado"]["vo"] == "243.80"
    terc = client.get(
        f"/v1/os/{orc['id']}/itens/{item['id']}/terceirizado",
        headers=auth(client, admin_token),
    )
    assert terc.status_code == 200, terc.text

    # E a conversão que antes falhava com 409 agora proceeds.
    conv = client.post(
        f"/v1/os/{orc['id']}/converter", headers=auth(client, admin_token)
    )
    assert conv.status_code == 200, conv.text
    assert conv.json()["data"]["orcamento_origem_id"] == orc["id"]


def test_put_validation_cliente_ou_avulso(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    orc, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    itens = [dict(item)]

    ambos = _put_orcamento(
        client, admin_token, orc["id"], cliente["id"], itens,
        cliente_nome_avulso="Outro nome",
    )
    assert ambos.status_code == 422, ambos.text

    nenhum = _put_orcamento(
        client, admin_token, orc["id"], None, itens, cliente_nome_avulso="  "
    )
    assert nenhum.status_code == 422, nenhum.text


def test_put_adiciona_e_remove_itens_sem_perder_os_demais(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    orc, item = _criar_os_com_item_fornecedor(client, admin_token, cliente)
    fornecedor = _criar_fornecedor(client, admin_token)
    _lancar(
        client, admin_token, orc["id"], item["id"], fornecedor["id"],
        "100.00", selecionada=True,
    )

    # Reenvia o item cotado + um novo item próprio.
    novo = {
        "descricao_avulsa": "Item acrescentado na edição",
        "quantidade": "1",
        "valor_unitario": "50.00",
    }
    resp = _put_orcamento(
        client, admin_token, orc["id"], cliente["id"], [dict(item), novo]
    )
    assert resp.status_code == 200, resp.text
    itens = resp.json()["data"]["itens"]
    assert len(itens) == 2
    assert itens[0]["estado_cotacao"] == "cotado"
    assert itens[1]["descricao_avulsa"] == "Item acrescentado na edição"

    # Remover o novo mantém o cotado (e o ID original).
    resp = _put_orcamento(
        client, admin_token, orc["id"], cliente["id"], [itens[0]]
    )
    assert resp.status_code == 200, resp.text
    itens = resp.json()["data"]["itens"]
    assert len(itens) == 1
    assert itens[0]["id"] == item["id"]
    assert itens[0]["estado_cotacao"] == "cotado"
