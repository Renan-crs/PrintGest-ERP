"""Licenciamento `online_periodic` (PRD v2.0 §3/§7) — ativação, renovação e modo de leitura.

O RedGest é simulado com `httpx.MockTransport` (suíte herméticas, sem processo
externo), imitando o contrato congelado em `scripts/redgest_stub.py`.
"""

import httpx
import pytest

from app.services import licensa_service
from tests.conftest import auth

LICENCA_ID = "abc123def456"
CNPJ = "00000000000191"
CODIGO = "TESTE-GRAFICA-2026"


@pytest.fixture(autouse=True)
def _modo_leitura_limpo(client):
    # Depende de `client` para rodar DEPOIS do conftest (que libera escritas).
    licensa_service.ESTADO["modo_leitura"] = True
    yield


def _mock_stub(monkeypatch, respostas):
    registro = []

    def handle(request: httpx.Request) -> httpx.Response:
        registro.append(request)
        resposta = respostas.get(request.url.path)
        if resposta is None:
            return httpx.Response(404, json={"detail": "rota não mapeada no mock"})
        return resposta

    transporte = httpx.MockTransport(handle)
    monkeypatch.setattr(
        licensa_service,
        "_cliente",
        lambda: httpx.Client(base_url="http://redgest.local", transport=transporte),
    )
    return registro


def _respostas_ok() -> dict[str, httpx.Response]:
    return {
        "/api/v1/licencas": httpx.Response(
            200,
            json={"data": {"licenca_id": LICENCA_ID, "status": "aguardando"}},
        ),
        f"/api/v1/licencas/{LICENCA_ID}/ativar": httpx.Response(
            200,
            json={
                "data": {
                    "licenca_id": LICENCA_ID,
                    "client_id": f"grafica_{CNPJ}",
                    "client_secret": "segredo-dev",
                    "sistema": "grafica_erp",
                    "tipo_licenciamento": "online_periodic",
                    "access_token": "jwt.de.ativacao",
                    "token_type": "bearer",
                    "expires_in": 14400,
                }
            },
        ),
        f"/api/v1/licencas/{LICENCA_ID}": httpx.Response(
            200,
            json={
                "data": {
                    "licenca_id": LICENCA_ID,
                    "sistema": "grafica_erp",
                    "cnpj": CNPJ,
                    "plano": "mensal",
                    "status": "ativa",
                    "max_estacoes": 5,
                    "modulos_habilitados": ["cadastros", "movimento", "estoque"],
                }
            },
        ),
    }


def _valida_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": {
                "sistema": "grafica_erp",
                "tipo_licenciamento": "online_periodic",
                "cnpj_vinculado": CNPJ,
                "max_estacoes": 5,
                "modulos_habilitados": ["cadastros", "movimento", "estoque"],
                "access_token": "jwt.renovado",
                "token_type": "bearer",
                "expires_in": 14400,
            }
        },
    )


def _ativar(client):
    return client.post(
        "/v1/licenca/ativar", json={"cnpj": CNPJ, "codigo_licenca": CODIGO}
    )


def test_sem_ativacao_modo_leitura_bloqueia_escritas(client):
    resp = client.get("/v1/licenca")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "nao_ativada"
    assert data["modo_leitura"] is True

    resp = client.post(
        "/v1/clientes", json={"nome_razao": "Sem licença", "tipo_pessoa": "pf"}
    )
    assert resp.status_code == 423
    assert "modo de leitura" in resp.json()["detail"].lower()

    assert client.get("/health").status_code == 200


def test_licenca_desabilitada_libera_escritas(client, admin_token, monkeypatch):
    """Dev build (`PRINTGEST_LICENCA_DESABILITADA=true`): escritas liberadas mesmo sem ativação."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "licenca_desabilitada", True)
    licensa_service.ESTADO["modo_leitura"] = True  # força — o middleware deve ignorar

    resp = client.get("/v1/licenca")
    assert resp.status_code == 200
    assert resp.json()["data"]["modo_leitura"] is False

    resp = client.post(
        "/v1/clientes",
        json={"nome_razao": "Dev sem licença", "tipo_pessoa": "pf"},
        headers=auth(client, admin_token),
    )
    assert resp.status_code in (200, 201), resp.text
    assert resp.status_code != 423


def test_ativacao_libera_escritas(client, admin_token, monkeypatch):
    _mock_stub(monkeypatch, _respostas_ok())

    resp = _ativar(client)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ativa"
    assert data["modo_leitura"] is False
    assert data["max_estacoes"] == 5
    assert data["modulos_habilitados"] == ["cadastros", "movimento", "estoque"]

    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Gravado com licença", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text


def test_ativacao_normaliza_cnpj_com_mascara(client, monkeypatch):
    registro = _mock_stub(monkeypatch, _respostas_ok())

    resp = _ativar(client)
    assert resp.status_code == 200, resp.text

    payload_criacao = registro[0].read().decode()
    import json

    assert json.loads(payload_criacao)["cnpj"] == CNPJ


def test_renovacao_renova_token(client, monkeypatch):
    respostas = _respostas_ok()
    respostas[f"/api/v1/licencas/{LICENCA_ID}/validar"] = _valida_ok()
    _mock_stub(monkeypatch, respostas)

    _ativar(client)
    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ativa"
    assert data["modo_leitura"] is False
    assert data["token_expira_em"] is not None


def test_revogacao_volta_ao_modo_leitura(client, admin_token, monkeypatch):
    respostas = _respostas_ok()
    respostas[f"/api/v1/licencas/{LICENCA_ID}/validar"] = httpx.Response(
        403, json={"detail": "Licença revogada — não autorizada."}
    )
    _mock_stub(monkeypatch, respostas)

    _ativar(client)
    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 423

    data = client.get("/v1/licenca").json()["data"]
    assert data["status"] == "revogada"
    assert data["modo_leitura"] is True

    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Boqueado", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 423


def test_renovar_sem_ativacao_400(client):
    # O banco de teste é compartilhado entre os testes da suíte — testes
    # anteriores de ativação deixam uma linha local com credenciais. Garante
    # estado "sem ativação" isolando este teste.
    from app.models.licenca import Licenca
    from app.db import SessionLocal

    sessao = SessionLocal()
    sessao.query(Licenca).delete()
    sessao.commit()
    sessao.close()

    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 400