"""Lógica de Caixa — abertura, movimentos, fechamento e integrações.

Cobre lacunas que a suíte anterior não provava: concorrência na abertura,
fechamento duplicado, sangria acima do saldo, isolamento por usuário,
fechamento automático e estorno no cancelamento de venda.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from app.db import SessionLocal
from app.models.core import Usuario
from app.models.enums import NivelAcesso, TipoMovCaixa
from app.models.financeiro import Caixa, MovimentoCaixa
from app.models.movimento import VendaBalcao
from app.schemas.financeiro import AbrirCaixaIn
from app.services import financeiro_service
from tests.conftest import auth
from tests.test_rbac import _criar_usuario, _login_usuario
from tests.test_vendas import _criar_produto, _entrada, _vender


@pytest.fixture(autouse=True)
def _limpar_caixas(client):
    def limpar():
        db = SessionLocal()
        try:
            db.query(VendaBalcao).update({VendaBalcao.caixa_id: None})
            db.query(MovimentoCaixa).delete()
            db.query(Caixa).delete()
            db.commit()
        finally:
            db.close()

    limpar()
    yield
    limpar()


def _abrir(client, token, valor=100):
    r = client.post(
        "/v1/financeiro/caixa/abrir",
        headers=auth(client, token),
        json={"valor_abertura": valor, "observacoes": "teste"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _saldo(caixa_id: int):
    db = SessionLocal()
    try:
        caixa = db.get(Caixa, caixa_id)
        return financeiro_service.caixa_out(db, caixa)["saldo_atual"]
    finally:
        db.close()


def test_fechamento_duplicado_e_movimento_em_caixa_fechado(client, admin_token):
    h = auth(client, admin_token)
    caixa = _abrir(client, admin_token)

    r = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar",
        headers=h,
        json={"valor_informado": 100},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["diferenca"] == "0.00"

    assert client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar",
        headers=h,
        json={"valor_informado": 100},
    ).status_code == 409
    assert client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento",
        headers=h,
        json={"tipo": "suprimento", "valor": 10},
    ).status_code == 409


def test_sangria_acima_do_saldo_e_rejeitada(client, admin_token):
    h = auth(client, admin_token)
    caixa = _abrir(client, admin_token)

    r = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento",
        headers=h,
        json={"tipo": "sangria", "valor": 150},
    )
    assert r.status_code == 400, r.text
    assert "Saldo insuficiente" in r.json()["detail"]
    assert _saldo(caixa["id"]) == 100

    r = client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento",
        headers=h,
        json={"tipo": "sangria", "valor": 40},
    )
    assert r.status_code == 200, r.text
    assert _saldo(caixa["id"]) == 60


def test_outro_usuario_nao_opera_caixa_alheio(client, admin_token):
    caixa = _abrir(client, admin_token)
    login, senha = _criar_usuario(client, admin_token, NivelAcesso.CAIXA)
    outro = auth(client, _login_usuario(client, login, senha))

    assert client.get(
        f"/v1/financeiro/caixa/{caixa['id']}/extrato", headers=outro
    ).status_code == 404
    assert client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento",
        headers=outro,
        json={"tipo": "suprimento", "valor": 10},
    ).status_code == 404
    assert client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar",
        headers=outro,
        json={"valor_informado": 100},
    ).status_code == 404


def test_abertura_concorrente_perdedor_recebe_409(client, admin_token):
    from app.core.config import settings

    db = SessionLocal()
    try:
        uid = db.query(Usuario).filter(Usuario.login == settings.admin_inicial_login).first().id
    finally:
        db.close()

    barreira = threading.Barrier(2)

    def tentar():
        sessao = SessionLocal()
        try:
            barreira.wait(timeout=10)
            financeiro_service.abrir_caixa(
                sessao, filial_id=1, usuario_id=uid,
                dados=AbrirCaixaIn(valor_abertura=0),
            )
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            sessao.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(tentar) for _ in range(2)]
        resultados = [f.result(timeout=30) for f in futuros]
    assert sorted(resultados) == [200, 409]


def test_fechamento_automatico_todas_as_filiais(client, admin_token):
    from app.models.core import Empresa, Filial

    _abrir(client, admin_token, valor=50)
    db = SessionLocal()
    try:
        empresa = db.query(Empresa).first()
        destino = Filial(empresa_id=empresa.id, nome=f"Filial Auto {uuid.uuid4().hex[:6]}")
        db.add(destino)
        db.commit()
        admin = db.query(Usuario).order_by(Usuario.id).first()
        db.add(
            Caixa(
                filial_id=destino.id, usuario_id=admin.id,
                status="aberto", valor_abertura=25,
            )
        )
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        fechados = financeiro_service.fechar_caixas_abertos_automaticamente(db)
    finally:
        db.close()
    assert fechados == 2

    db = SessionLocal()
    try:
        caixas = db.query(Caixa).filter(Caixa.status == "fechado").all()
        assert len(caixas) == 2
        for caixa in caixas:
            assert caixa.valor_informado == caixa.valor_esperado
            assert caixa.diferenca == 0
    finally:
        db.close()


def test_cancelamento_venda_estorna_o_caixa(client, admin_token):
    caixa = _abrir(client, admin_token, valor=0)
    produto = _criar_produto(client, admin_token)
    _entrada(client, admin_token, produto["id"], 10)
    venda = _vender(client, admin_token, produto["id"], quantidade=3).json()["data"]
    assert _saldo(caixa["id"]) == 60

    r = client.delete(
        f"/v1/vendas/{venda['id']}", headers=auth(client, admin_token)
    )
    assert r.status_code == 204, r.text
    assert _saldo(caixa["id"]) == 0

    db = SessionLocal()
    try:
        tipos = [
            m.tipo for m in db.query(MovimentoCaixa)
            .filter(MovimentoCaixa.caixa_id == caixa["id"]).all()
        ]
    finally:
        db.close()
    assert tipos.count(TipoMovCaixa.ENTRADA) == 1
    assert tipos.count(TipoMovCaixa.SAIDA) == 1


def test_validacoes_de_schema(client, admin_token):
    h = auth(client, admin_token)
    assert client.post(
        "/v1/financeiro/caixa/abrir", headers=h,
        json={"valor_abertura": -1},
    ).status_code == 422

    caixa = _abrir(client, admin_token)
    assert client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/fechar", headers=h,
        json={"valor_informado": -1},
    ).status_code == 422
    assert client.post(
        f"/v1/financeiro/caixa/{caixa['id']}/movimento", headers=h,
        json={"tipo": "suprimento", "valor": 0},
    ).status_code == 422
