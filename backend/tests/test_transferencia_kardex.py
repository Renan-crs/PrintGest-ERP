"""Kardex de transferência deve registrar o par saldo anterior → posterior.

Regressão: `_movimentar` lia o saldo DEPOIS do UPDATE, então uma saída de 3 de
um saldo 10 gravava anterior=7 e posterior=4 (em vez de 10 → 7).
"""

from decimal import Decimal

from app.db import SessionLocal
from app.models.cadastros import MovimentoEstoque
from app.models.core import Empresa, Filial
from app.models.enums import OrigemMov
from tests.conftest import auth
from tests.test_variacoes_estoque import _entrada, _produto, _u


def _criar_filial_destino():
    db = SessionLocal()
    try:
        empresa = db.query(Empresa).first()
        destino = Filial(empresa_id=empresa.id, nome=f"Filial Kardex {_u()}")
        db.add(destino)
        db.commit()
        return destino.id
    finally:
        db.close()


def _movimentos(filial_id: int, produto_id: int, origem: str):
    db = SessionLocal()
    try:
        return [
            {
                "anterior": m.saldo_anterior,
                "posterior": m.saldo_posterior,
                "quantidade": m.quantidade,
            }
            for m in db.query(MovimentoEstoque).filter(
                MovimentoEstoque.filial_id == filial_id,
                MovimentoEstoque.produto_id == produto_id,
                MovimentoEstoque.origem == origem,
            ).all()
        ]
    finally:
        db.close()


def test_listagem_transferencias_total_e_paginacao(client, admin_token):
    """`meta.total` deve ser o total real, não o tamanho da página."""
    h = auth(client, admin_token)
    destino_id = _criar_filial_destino()
    produto = _produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 20)

    for _ in range(2):
        r = client.post(
            "/v1/estoque/transferencias",
            headers=h,
            json={
                "filial_destino_id": destino_id,
                "produto_id": produto["id"],
                "quantidade": 1,
            },
        )
        assert r.status_code == 201, r.text

    r = client.get(
        "/v1/estoque/transferencias", headers=h, params={"limit": 1, "offset": 0}
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert len(corpo["data"]) == 1
    assert corpo["meta"]["total"] >= 2


def test_kardex_transferencia_saida_e_entrada(client, admin_token):
    h = auth(client, admin_token)
    destino_id = _criar_filial_destino()
    produto = _produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)

    resp = client.post(
        "/v1/estoque/transferencias",
        headers=h,
        json={
            "filial_destino_id": destino_id,
            "produto_id": produto["id"],
            "quantidade": 3,
        },
    )
    assert resp.status_code == 201, resp.text
    doc = resp.json()["data"]

    saidas = _movimentos(1, produto["id"], OrigemMov.TRANSFERENCIA_SAIDA)
    assert saidas, "saída da transferência não gravou kardex"
    ultima = saidas[-1]
    assert Decimal(str(ultima["anterior"])) == Decimal("10")
    assert Decimal(str(ultima["posterior"])) == Decimal("7")
    assert Decimal(str(ultima["quantidade"])) == Decimal("3")

    # Confirmação direta no serviço (a filial do admin não é a de destino).
    from app.services import transferencia_service

    db = SessionLocal()
    try:
        transferencia_service.confirmar_recebimento(
            db, item_id=doc["id"], filial_id=destino_id, usuario_id=1
        )
    finally:
        db.close()

    entradas = _movimentos(destino_id, produto["id"], OrigemMov.TRANSFERENCIA_ENTRADA)
    assert entradas, "confirmação não gravou kardex de entrada"
    ultima_entrada = entradas[-1]
    assert Decimal(str(ultima_entrada["anterior"])) == Decimal("0")
    assert Decimal(str(ultima_entrada["posterior"])) == Decimal("3")
