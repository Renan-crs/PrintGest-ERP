"""VF do fornecedor pode ser unitário ou TOTAL da quantidade pedida.

Caso do negócio: R$ 35,00 é o valor cobrado por 24 adesivos de vinil
transparente. O unitário é R$ 3,56 (informativo) e o total da linha é R$ 85,33 —
não R$ 2.047,92 como no cálculo antigo que tratava o VF como unitário.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import precificacao
from tests.conftest import auth
from tests.test_cotacao_os import (
    _criar_cliente,
    _criar_fornecedor,
    _criar_os_com_item_fornecedor,
    _lancar,
)


def test_snapshot_vf_total_24_unidades():
    snap = precificacao.snapshot_item_terceirizado(
        Decimal("35.00"), Decimal(130), Decimal(6), quantidade=24, vf_tipo="total"
    )
    assert snap["vf_tipo"] == "total"
    assert snap["quantidade"] == "24"
    assert snap["cp"] == "80.50"
    assert snap["vo"] == "85.33"
    assert snap["vo_total"] == "85.33"
    assert snap["vo_unitario"] == "3.5554"


def test_snapshot_unitario_permanece_legado():
    snap = precificacao.snapshot_item_terceirizado(
        Decimal("87.35"), Decimal(130), Decimal(6), quantidade=1
    )
    assert snap["vf_tipo"] == "unitario"
    assert snap["vo"] == "212.96"
    assert snap["vo_total"] == "212.96"
    assert snap["vo_unitario"] == "212.96"


def test_vf_total_sem_quantidade_e_invalido():
    with pytest.raises(ValueError, match="quantidade"):
        precificacao.snapshot_item_terceirizado(
            Decimal("35"), Decimal(130), Decimal(6), vf_tipo="total"
        )
    with pytest.raises(ValueError, match="inválido"):
        precificacao.snapshot_item_terceirizado(
            Decimal("35"), Decimal(130), Decimal(6), vf_tipo="por_lote"
        )


def test_cotacao_vf_total_ao_lancar(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_obj, item = _criar_os_com_item_fornecedor(
        client,
        admin_token,
        cliente,
        itens=[
            {
                "produto_id": None,
                "descricao_avulsa": "Adesivo Vinil Transparente 5x5",
                "quantidade": 24,
                "valor_unitario": 0,
                "tipo": "fornecedor",
            }
        ],
    )

    resp = _lancar(
        client,
        admin_token,
        os_obj["id"],
        item["id"],
        fornecedor["id"],
        "35.00",
        vf_tipo="total",
        selecionada=True,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["vf_tipo"] == "total"

    detalhe = client.get(
        f"/v1/os/{os_obj['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    item_salvo = detalhe["itens"][0]
    assert item_salvo["valor_unitario"] == "3.56"
    assert item_salvo["valor_total"] == "85.33"
    assert detalhe["valor_total"] == "85.33"
    comparativo = client.get(
        f"/v1/os/{os_obj['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, admin_token),
    ).json()
    snap = comparativo["selecionado"]
    assert snap["vf_tipo"] == "total"
    assert snap["vo_total"] == "85.33"
    assert snap["vo_unitario"] == "3.5554"


def test_selecionar_cotacao_vf_total_preserva_tipo(client, admin_token):
    """O tipo precisa persistir: PUT /selecionar não recebe corpo."""
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_obj, item = _criar_os_com_item_fornecedor(
        client,
        admin_token,
        cliente,
        itens=[
            {
                "produto_id": None,
                "descricao_avulsa": "Adesivo Vinil",
                "quantidade": 24,
                "valor_unitario": 0,
                "tipo": "fornecedor",
            }
        ],
    )
    lancada = _lancar(
        client,
        admin_token,
        os_obj["id"],
        item["id"],
        fornecedor["id"],
        "35.00",
        vf_tipo="total",
    )
    assert lancada.status_code == 201, lancada.text
    cotacao_id = lancada.json()["data"]["id"]

    selecionada = client.put(
        f"/v1/os/{os_obj['id']}/itens/{item['id']}/cotacoes/{cotacao_id}/selecionar",
        headers=auth(client, admin_token),
    )
    assert selecionada.status_code == 200, selecionada.text

    detalhe = client.get(
        f"/v1/os/{os_obj['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert detalhe["itens"][0]["valor_total"] == "85.33"
    comparativo = client.get(
        f"/v1/os/{os_obj['id']}/itens/{item['id']}/cotacoes",
        headers=auth(client, admin_token),
    ).json()
    assert comparativo["selecionado"]["vf_tipo"] == "total"
    assert comparativo["selecionado"]["vo_total"] == "85.33"


def test_vf_unitario_continua_multiplicando_quantidade(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    fornecedor = _criar_fornecedor(client, admin_token)
    os_obj, item = _criar_os_com_item_fornecedor(
        client,
        admin_token,
        cliente,
        itens=[
            {
                "produto_id": None,
                "descricao_avulsa": "Serviço unitário",
                "quantidade": 24,
                "valor_unitario": 0,
                "tipo": "fornecedor",
            }
        ],
    )
    resp = _lancar(
        client,
        admin_token,
        os_obj["id"],
        item["id"],
        fornecedor["id"],
        "35.00",
        vf_tipo="unitario",
        selecionada=True,
    )
    assert resp.status_code == 201, resp.text
    detalhe = client.get(
        f"/v1/os/{os_obj['id']}", headers=auth(client, admin_token)
    ).json()["data"]
    assert detalhe["itens"][0]["valor_unitario"] == "85.33"
    assert detalhe["itens"][0]["valor_total"] == "2047.92"
