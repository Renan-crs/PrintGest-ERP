"""Emissão fiscal via gateway de terceiro (NFC-e/NF-e/NFS-e).

O gateway é mockado com `httpx.MockTransport`: nenhuma chamada de rede real,
nenhuma credencial no repositório. Cobrem-se emissão, idempotência, consulta,
cancelamento, falha/contingência, auditoria e isolamento por filial.
"""

import json
import uuid

import httpx
from sqlalchemy import text as sa_text

from app.core.config import Settings, settings
from app.db import SessionLocal
from app.models.enums import ModeloFiscal, StatusFiscal
from app.models.fiscal import FiscalEvento
from app.services import fiscal_gateway, fiscal_service
from tests.conftest import auth

FILIAL = 1

def _chave() -> str:
    """Chave única por emissão — o banco de teste é compartilhado entre casos."""
    return (uuid.uuid4().hex * 3)[:44]


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _handler_sucesso(monitor: dict) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        monitor.setdefault("chamadas", []).append(
            (request.method, request.url.path, json.loads(request.content or b"{}"))
        )
        caminho = request.url.path
        if caminho == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.method == "POST" and caminho == "/documentos":
            chave = monitor.setdefault("chaves", [])
            chave.append(_chave())
            return httpx.Response(
                201,
                json={
                    "id": f"gw-{len(chave)}",
                    "status": "autorizado",
                    "chave_acesso": chave[-1],
                    "numero": int(uuid.uuid4().hex[:8], 16) % 1_000_000 + 1,
                    "serie": 1,
                    "protocolo": "prot-123",
                    "mensagem": "Documento autorizado",
                    "xml_url": "https://gw.test/xml/gw-123",
                    "danfe_url": "https://gw.test/danfe/gw-123",
                },
            )
        if request.method == "GET" and caminho.startswith("/documentos/"):
            return httpx.Response(
                200,
                json={
                    "id": "gw-1",
                    "status": "autorizado",
                    "chave_acesso": monitor.get("chaves", [""])[0],
                    "protocolo": "prot-123",
                },
            )
        if request.method == "POST" and caminho.endswith("/cancelamento"):
            return httpx.Response(
                200, json={"id": "gw-1", "status": "cancelado", "token": "segredo"}
            )
        return httpx.Response(404, json={"detail": "rota inesperada"})

    return httpx.MockTransport(handler)


def _mockar_gateway(monkeypatch, transport: httpx.MockTransport) -> dict:
    monitor: dict = {}
    cfg = Settings(
        _env_file=None,
        fiscal_gateway_url="https://gw.test",
        fiscal_gateway_token="tok-teste",
        fiscal_gateway_health_path="/health",
    )
    fabrica = lambda **kwargs: fiscal_gateway.FiscalGateway(
        config=cfg, client=httpx.Client(transport=transport), **kwargs
    )
    monkeypatch.setattr(fiscal_service, "FiscalGateway", fabrica)
    monkeypatch.setattr(settings, "fiscal_gateway_url", cfg.fiscal_gateway_url)
    monkeypatch.setattr(settings, "fiscal_gateway_token", cfg.fiscal_gateway_token)
    fiscal_service.invalidar_cache_disponibilidade()
    return monitor


def _criar_venda(client, admin_token) -> int:
    resp = client.post(
        "/v1/vendas",
        headers=auth(client, admin_token),
        json={
            "cliente_nome_avulso": "Cliente P3",
            "forma_pagamento": "dinheiro",
            "valor_recebido": "100.00",
            "itens": [
                {
                    "descricao_avulsa": "Serviço de impressão",
                    "quantidade": "1",
                    "valor_unitario": "80.00",
                    "desconto": "0",
                }
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _criar_cliente(client, admin_token) -> int:
    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": f"Cliente {_u()}", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _eventos(doc_id: int) -> list[str]:
    db = SessionLocal()
    try:
        return [
            e.tipo
            for e in db.query(FiscalEvento)
            .filter(FiscalEvento.documento_fiscal_id == doc_id)
            .order_by(FiscalEvento.id)
            .all()
        ]
    finally:
        db.close()


def test_sem_gateway_emissao_indisponivel(client, admin_token, caixa_admin):
    headers = auth(client, admin_token)
    # Config default da suíte não tem URL de gateway.
    resumo = client.get("/v1/fiscal/resumo", headers=headers).json()["data"]
    assert resumo["gateway_configurado"] is False
    assert "gateway fiscal" in resumo["mensagem"].lower()

    venda_id = _criar_venda(client, admin_token)
    resp = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfce", "venda_balcao_id": venda_id},
    )
    assert resp.status_code == 503


def test_emissao_nfce_e_idempotencia(client, admin_token, caixa_admin, monkeypatch):
    monitor: dict = {}
    _mockar_gateway(monkeypatch, _handler_sucesso(monitor))
    headers = auth(client, admin_token)
    venda_id = _criar_venda(client, admin_token)

    resp = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfce", "venda_balcao_id": venda_id},
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["data"]
    assert doc["status"] == StatusFiscal.AUTORIZADO.value
    assert doc["chave_acesso"] == monitor["chaves"][0]
    assert doc["gateway_id"] == "gw-1"
    assert doc["protocolo"] == "prot-123"
    assert doc["ambiente"] == "homologacao"
    assert "emissao_iniciada" in _eventos(doc["id"])
    assert "emitido" in _eventos(doc["id"])

    # payload montado a partir da venda (sem credenciais)
    envio = [c for c in monitor["chamadas"] if c[0] == "POST" and c[1] == "/documentos"]
    assert len(envio) == 1
    payload = envio[0][2]
    assert payload["modelo"] == "nfce"
    assert payload["referencia"]["id"] == venda_id
    assert payload["itens"][0]["descricao"] == "Serviço de impressão"

    segunda = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfce", "venda_balcao_id": venda_id},
    )
    assert segunda.status_code == 200
    assert segunda.json()["data"]["id"] == doc["id"]
    assert len(
        [c for c in monitor["chamadas"] if c[0] == "POST" and c[1] == "/documentos"]
    ) == 1


def test_consulta_cancelamento_e_auditoria(client, admin_token, caixa_admin, monkeypatch):
    monitor: dict = {}
    _mockar_gateway(monkeypatch, _handler_sucesso(monitor))
    headers = auth(client, admin_token)
    venda_id = _criar_venda(client, admin_token)
    doc = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfce", "venda_balcao_id": venda_id},
    ).json()["data"]

    consulta = client.post(
        f"/v1/fiscal/documentos/{doc['id']}/consultar", headers=headers
    )
    assert consulta.status_code == 200, consulta.text
    assert consulta.json()["data"]["ultima_consulta_em"]

    cancelar = client.post(
        f"/v1/fiscal/documentos/{doc['id']}/cancelar",
        headers=headers,
        json={"motivo": "Cancelamento pelo cliente"},
    )
    assert cancelar.status_code == 200, cancelar.text
    cancelado = cancelar.json()["data"]
    assert cancelado["status"] == StatusFiscal.CANCELADO.value
    assert cancelado["motivo_cancelamento"] == "Cancelamento pelo cliente"
    assert cancelado["cancelado_em"]

    tipos = _eventos(doc["id"])
    assert "consulta" in tipos
    assert "cancelamento" in tipos

    # token do retorno do gateway não vaza na auditoria
    eventos = client.get(
        f"/v1/fiscal/documentos/{doc['id']}/eventos", headers=headers
    ).json()["data"]
    assert all("segredo" not in json.dumps(e) for e in eventos)


def test_emissao_nfse_de_os(client, admin_token, monkeypatch):
    monitor: dict = {}
    _mockar_gateway(monkeypatch, _handler_sucesso(monitor))
    headers = auth(client, admin_token)
    cliente_id = _criar_cliente(client, admin_token)
    os_resp = client.post(
        "/v1/os",
        headers=headers,
        json={
            "cliente_id": cliente_id,
            "forma_pagamento": "pix",
            "itens": [
                {
                    "descricao_avulsa": "Impressão de cartões",
                    "quantidade": "2",
                    "valor_unitario": "50.00",
                    "desconto": "0",
                }
            ],
        },
    )
    assert os_resp.status_code == 200, os_resp.text
    os_id = os_resp.json()["data"]["id"]

    resp = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfse", "ordem_servico_id": os_id},
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["data"]
    assert doc["modelo"] == "nfse"
    assert doc["status"] == StatusFiscal.AUTORIZADO.value
    envios = [
        c for c in monitor["chamadas"] if c[0] == "POST" and c[1] == "/documentos"
    ]
    assert envios[0][2]["modelo"] == "nfse"
    assert envios[0][2]["referencia"]["tipo"] == "ordem_servico"


def test_falha_do_gateway_gera_contingencia_e_evento(
    client, admin_token, caixa_admin, monkeypatch
):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "gateway indisponível"})

    _mockar_gateway(monkeypatch, httpx.MockTransport(handler))
    headers = auth(client, admin_token)
    venda_id = _criar_venda(client, admin_token)
    resp = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfce", "venda_balcao_id": venda_id, "contingencia": True},
    )
    assert resp.status_code == 200, resp.text
    doc = resp.json()["data"]
    assert doc["status"] == StatusFiscal.CONTINGENCIADO.value
    assert doc["contingencia"] is True
    assert "emissao_falhou" in _eventos(doc["id"])


def test_documento_de_outra_filial_nao_e_visivel(
    client, admin_token, caixa_admin, monkeypatch
):
    monitor: dict = {}
    _mockar_gateway(monkeypatch, _handler_sucesso(monitor))
    headers = auth(client, admin_token)
    venda_id = _criar_venda(client, admin_token)
    doc = client.post(
        "/v1/fiscal/documentos/emitir",
        headers=headers,
        json={"modelo": "nfce", "venda_balcao_id": venda_id},
    ).json()["data"]

    db = SessionLocal()
    try:
        from app.models.core import Empresa, Filial

        empresa = Empresa(
            razao_social="Outra gráfica", cnpj=uuid.uuid4().hex[:14], ativa=True
        )
        db.add(empresa)
        db.flush()
        filial = Filial(empresa_id=empresa.id, nome="Outra filial", ativa=True)
        db.add(filial)
        db.flush()
        db.execute(
            sa_text(
                "UPDATE documento_fiscal SET filial_id = :filial WHERE id = :id"
            ),
            {"filial": filial.id, "id": doc["id"]},
        )
        db.commit()
    finally:
        db.close()

    assert client.get(
        f"/v1/fiscal/documentos/{doc['id']}", headers=headers
    ).status_code == 404
    assert client.post(
        f"/v1/fiscal/documentos/{doc['id']}/consultar", headers=headers
    ).status_code == 404
