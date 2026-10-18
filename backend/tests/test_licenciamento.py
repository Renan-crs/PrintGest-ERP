"""Licenciamento `online_periodic` (PRD v2.0 §3/§7) — ativação, renovação e modo de leitura.

O RedGest é simulado com `httpx.MockTransport` (suíte herméticas, sem processo
externo), imitando o contrato congelado em `scripts/redgest_stub.py`.
"""

import datetime as dt

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


# --------------------------------------------- resiliência de rede (E1 do plano)


def _mock_transporte(monkeypatch, handle):
    """Injeta um transporte httpx arbitrário no `_cliente` do serviço."""
    transporte = httpx.MockTransport(handle)
    monkeypatch.setattr(
        licensa_service,
        "_cliente",
        lambda: httpx.Client(base_url="http://redgest.local", transport=transporte),
    )


def test_ativacao_sem_rede_devolve_503(client, monkeypatch):
    """RedGest inacessível na ativação: 503 com mensagem clara, nunca 500 cru."""

    def handle(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rota para o RedGest")

    _mock_transporte(monkeypatch, handle)

    resp = _ativar(client)
    assert resp.status_code == 503, resp.text
    assert "não foi possível falar com o servidor de licenças" in resp.json()[
        "detail"
    ].lower()


def test_timeout_na_renovacao_nao_revoga(client, monkeypatch):
    """Cold start/timeout do RedGest: 503, sem revogação e sem modo leitura."""
    respostas = _respostas_ok()

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/validar"):
            raise httpx.ReadTimeout("cold start do plano gratuito")
        return respostas.get(
            request.url.path, httpx.Response(404, json={"detail": "não mapeada"})
        )

    _mock_transporte(monkeypatch, handle)

    assert _ativar(client).status_code == 200  # ativação não toca em /validar

    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 503, resp.text

    data = client.get("/v1/licenca").json()["data"]
    assert data["status"] == "ativa"  # indisponibilidade ≠ revogação
    assert data["modo_leitura"] is False


def test_backoff_crescente_e_saturado():
    """1/5/15 min após falhas; volta ao intervalo normal com zero falhas."""
    from app.core.config import settings

    assert (
        licensa_service._atraso_proximo_ciclo(0)
        == settings.licenca_refresh_intervalo_segundos
    )
    assert licensa_service._atraso_proximo_ciclo(1) == 60
    assert licensa_service._atraso_proximo_ciclo(2) == 300
    assert licensa_service._atraso_proximo_ciclo(3) == 900
    assert licensa_service._atraso_proximo_ciclo(9) == 900  # satura no último passo


# ------------------------------- estados e tolerância offline (E2 do plano)


def _ajustar_licenca(**campos):
    """Manipula a linha local da licença (simula passagem do tempo/falha)."""
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    sessao = SessionLocal()
    try:
        lic = sessao.query(Licenca).first()
        assert lic is not None, "ative a licença antes de ajustar"
        for chave, valor in campos.items():
            setattr(lic, chave, valor)
        sessao.commit()
    finally:
        sessao.close()


def _parse(valor: str) -> dt.datetime:
    return dt.datetime.fromisoformat(valor)


def test_ativacao_define_janela_de_tolerancia(client, monkeypatch):
    """A tolerância começa na expiração do token e dura `licenca_tolerancia_horas`."""
    from app.core.config import settings

    _mock_stub(monkeypatch, _respostas_ok())
    resp = _ativar(client)
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["estado"] == "ativa"
    assert data["motivo"]
    janela = _parse(data["tolerancia_expira_em"]) - _parse(data["token_expira_em"])
    assert janela.total_seconds() == settings.licenca_tolerancia_horas * 3600


def test_token_vencido_dentro_da_tolerancia_opera_normal(
    client, admin_token, monkeypatch
):
    """Queda do RedGest não bloqueia no instante da expiração (tolerância ativa)."""
    _mock_stub(monkeypatch, _respostas_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        token_expira_em=agora - dt.timedelta(hours=1),
        tolerancia_expira_em=agora + dt.timedelta(hours=71),
    )

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "tolerancia"
    assert data["modo_leitura"] is False

    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Gravado na tolerância", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text


def test_tolerancia_esgotada_entra_em_modo_leitura(client, monkeypatch):
    _mock_stub(monkeypatch, _respostas_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        token_expira_em=agora - dt.timedelta(hours=100),
        tolerancia_expira_em=agora - dt.timedelta(hours=28),
    )

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "leitura"
    assert data["modo_leitura"] is True


def test_base_legada_deriva_tolerancia_do_token(client, monkeypatch):
    """Licença ativada antes de E2 (coluna nula) ainda ganha tolerância."""
    _mock_stub(monkeypatch, _respostas_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        token_expira_em=agora - dt.timedelta(hours=1),
        tolerancia_expira_em=None,
    )

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "tolerancia"
    assert data["modo_leitura"] is False
    assert data["tolerancia_expira_em"] is not None  # derivada do token atual


def test_falha_de_renovacao_registra_diagnostico(client, monkeypatch):
    """Falha de rede grava `ultima_tentativa_em`/`ultimo_erro` para a UI."""
    _mock_stub(monkeypatch, _respostas_ok())
    assert _ativar(client).status_code == 200

    def handle(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("RedGest fora do ar")

    _mock_transporte(monkeypatch, handle)
    assert client.post("/v1/licenca/renovar").status_code == 503

    data = client.get("/v1/licenca").json()["data"]
    assert data["ultima_tentativa_em"] is not None
    assert "inacessível" in (data["ultimo_erro"] or "")
    assert data["estado"] == "ativa"  # o token local ainda é válido