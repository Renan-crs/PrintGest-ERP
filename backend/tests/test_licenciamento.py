"""Licenciamento por chave de produto (RedGest Contrato C) — PRD v2.0 §3/§7.

A validação online é simulada com `httpx.MockTransport` (suíte hermética, sem
processo externo). O mock **confere a assinatura HMAC** exatamente como o
RedGest faria (contrato congelado em
`apps/liberacao/infrastructure/web/licenca_software_auth.py`), então um erro de
assinatura no serviço quebra o teste.
"""

import datetime as dt
import hashlib
import hmac
import http.server
import json
import threading
import time

import httpx
import pytest

from app.core import cofre
from app.core.config import settings
from app.services import licensa_service
from tests.conftest import auth

CHAVE = "A1B2-C3D4-E5F6-7890"
CHAVE_INVALIDA = "0000-0000-0000-0000"
API_KEY = "chave-api-do-sistema-teste"
CAMINHO = "/api/v1/licencas-software/validar/"
# SHA-256 fixo de 64 hex — usado como `maquina_fingerprint` nos testes.
FINGERPRINT_FIXO = "a" * 64


@pytest.mark.parametrize(
    "configurado, esperado",
    [
        ("http://127.0.0.1:9100", "http://127.0.0.1:9100"),
        ("http://127.0.0.1:9100/", "http://127.0.0.1:9100"),
        ("https://redgest.exemplo.com/api/v1/", "https://redgest.exemplo.com"),
        ("https://redgest.exemplo.com/api/v1", "https://redgest.exemplo.com"),
        ("https://redgest.exemplo.com/API/V1//", "https://redgest.exemplo.com"),
    ],
)
def test_base_redgest_nao_duplica_o_prefixo_da_api(
    monkeypatch, configurado, esperado
):
    """A URL configurada não pode carregar o path da API.

    Os caminhos de cada contrato já incluem `/api/v1/...`. Se o operador colar a
    URL com esse sufixo, o `httpx` concatena e a chamada vira
    `/api/v1/api/v1/...` — 404 que a UI mostraria como falha de licença.
    """
    monkeypatch.setattr(settings, "redgest_url", configurado)
    assert licensa_service._base_redgest() == esperado


@pytest.fixture(autouse=True)
def _licenca_isolada(client, monkeypatch):
    """Roda DEPOIS do conftest: limpa a licença local e configura o segredo HMAC."""
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    monkeypatch.setattr(settings, "redgest_api_key", API_KEY)
    monkeypatch.setattr(settings, "licenca_desabilitada", False)
    # Fingerprint fixo: a suíte não pode depender do hardware da máquina nem
    # disparar o PowerShell (doc de integração §7).
    monkeypatch.setattr(settings, "maquina_fingerprint", FINGERPRINT_FIXO)

    sessao = SessionLocal()
    try:
        sessao.query(Licenca).delete()
        sessao.commit()
    finally:
        sessao.close()

    licensa_service.ESTADO["modo_leitura"] = True
    licensa_service._fingerprint_do_hardware.cache_clear()
    licensa_service._abrir_chave.cache_clear()
    yield


# ------------------------------------------------------------------- helpers
def _iso(quando: dt.datetime) -> str:
    return quando.isoformat()


def _resposta_ok(**overrides) -> httpx.Response:
    corpo = {
        "valido": True,
        "expira_em": _iso(licensa_service._agora() + dt.timedelta(days=30)),
        "primeira_ativacao": True,
        "ativacoes_realizadas": 1,
        "limite_ativacoes": 3,
    }
    corpo.update(overrides)
    return httpx.Response(200, json=corpo)


def _mock(monkeypatch, resposta):
    """Injeta um RedGest falso; devolve o registro das requisições recebidas."""
    registro: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        registro.append(request)
        return resposta(request) if callable(resposta) else resposta

    transporte = httpx.MockTransport(handle)
    monkeypatch.setattr(
        licensa_service,
        "_cliente",
        lambda: httpx.Client(base_url="http://redgest.local", transport=transporte),
    )
    return registro


def _mock_sem_rede(monkeypatch, erro: Exception | None = None):
    def handle(_request: httpx.Request) -> httpx.Response:
        raise erro or httpx.ConnectError("sem rota para o RedGest")

    return _mock(monkeypatch, handle)


class _RedGestReal:
    """Servidor HTTP local (socket real) que responde com atraso configurável.

    O `MockTransport` do httpx **não** aplica timeout ao handler — ele devolve a
    resposta na hora, então um `time.sleep` no mock nunca estoura o timeout do
    cliente. Para exercitar o *cold start* de verdade (a requisição estourar
    `licenca_timeout_segundos`) é preciso um transporte real; este servidor
    dorme antes de responder e ainda permite trocar o atraso entre chamadas.
    """

    def __init__(self, *, atraso: float = 0.0) -> None:
        self.atraso = atraso
        self.requisicoes: list[dict] = []
        dono = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 (nome fixado pelo stdlib)
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho)
                dono.requisicoes.append(
                    {
                        "caminho": self.path,
                        "corpo": corpo,
                        "headers": dict(self.headers),
                    }
                )
                time.sleep(dono.atraso)
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    payload = _resposta_ok().content
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionError):
                    # O cliente já desistiu (timeout): é exatamente o que o
                    # teste de cold start quer medir.
                    pass

            def log_message(self, *args):  # silencia o log do stdlib
                pass

        self.servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.servidor.server_address[1]}"
        self.thread = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.servidor.shutdown()
        self.servidor.server_close()


def _ativar(client, chave: str = CHAVE):
    return client.post("/v1/licenca/ativar", json={"chave_ativacao": chave})


def _assinatura_esperada(request: httpx.Request) -> str:
    nonce = request.headers["X-RedGest-Nonce"]
    timestamp = request.headers["X-RedGest-Timestamp"]
    material = f"{nonce}{timestamp}".encode("utf-8") + request.read()
    digest = hmac.new(API_KEY.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _ajustar_licenca(**campos):
    """Manipula a linha local da licença (simula passagem do tempo/estado)."""
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


# ------------------------------------------------------- ativação obrigatória
def test_sem_ativacao_modo_leitura_bloqueia_escritas(client):
    resp = client.get("/v1/licenca")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "nao_ativada"
    assert data["estado"] == "nao_ativada"
    assert data["modo_leitura"] is True

    resp = client.post(
        "/v1/clientes", json={"nome_razao": "Sem licença", "tipo_pessoa": "pf"}
    )
    assert resp.status_code == 423
    assert "modo de leitura" in resp.json()["detail"].lower()

    assert client.get("/health").status_code == 200


def test_licenca_desabilitada_libera_escritas(client, admin_token, monkeypatch):
    monkeypatch.setattr(settings, "licenca_desabilitada", True)

    resp = client.get("/v1/licenca")
    assert resp.status_code == 200
    assert resp.json()["data"]["modo_leitura"] is False

    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Gravado em dev", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 200, resp.text


def test_ativacao_online_libera_escritas(client, admin_token, monkeypatch):
    _mock(monkeypatch, _resposta_ok())

    resp = _ativar(client)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ativa"
    assert data["estado"] == "ativa"
    assert data["modo_leitura"] is False
    assert data["limite_ativacoes"] == 3
    assert data["ativacoes_realizadas"] == 1
    assert data["expira_em"] is not None
    assert data["chave"].endswith("7890")
    assert "A1B2" not in data["chave"]  # a chave é mascarada na resposta

    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Gravado com licença", "tipo_pessoa": "pj"},
    )
    assert resp.status_code == 200, resp.text


def test_ativacao_assa_requisicao_em_conformidade(client, monkeypatch):
    """Assinatura HMAC, nonce/timestamp e corpo exatos do manual do RedGest."""
    registro = _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    req = registro[0]
    assert req.method == "POST"
    assert req.url.path == CAMINHO
    assert req.headers["X-RedGest-Signature"] == _assinatura_esperada(req)
    assert req.headers["X-RedGest-Signature"].startswith("sha256=")
    assert req.headers["X-RedGest-Nonce"]
    assert req.headers["X-RedGest-Timestamp"].endswith("Z")

    corpo = json.loads(req.read())
    assert corpo["chave_ativacao"] == CHAVE
    assert corpo["maquina_fingerprint"] == licensa_service._fingerprint()


def test_ativacao_normaliza_chave_minuscula(client, monkeypatch):
    registro = _mock(monkeypatch, _resposta_ok())
    assert _ativar(client, chave=CHAVE.lower()).status_code == 200
    assert json.loads(registro[0].read())["chave_ativacao"] == CHAVE


def test_ativacao_aceita_serial_sem_hifens(client, monkeypatch):
    """Doc §4.2: o usuário pode colar o serial sem hífens."""
    registro = _mock(monkeypatch, _resposta_ok())
    assert _ativar(client, chave="a1b2c3d4e5f67890").status_code == 200
    assert json.loads(registro[0].read())["chave_ativacao"] == CHAVE


def test_ativacao_aceita_serial_com_espacos(client, monkeypatch):
    registro = _mock(monkeypatch, _resposta_ok())
    assert _ativar(client, chave=" A1B2 C3D4 E5F6 7890 ").status_code == 200
    assert json.loads(registro[0].read())["chave_ativacao"] == CHAVE


def test_serial_invalido_devolve_400_sem_chamar_redgest(client, monkeypatch):
    """Formato avaliado localmente (doc §4.2): não gasta tentativa da cota."""
    registro = _mock(monkeypatch, _resposta_ok())
    resp = _ativar(client, chave="A1B2-C3D4")
    assert resp.status_code == 400, resp.text
    assert "xxxx-xxxx-xxxx-xxxx" in resp.json()["detail"].lower()
    assert registro == []


def test_parse_chave_normaliza_e_valida():
    assert licensa_service._parse_chave("a1b2c3d4e5f67890") == CHAVE
    assert licensa_service._parse_chave(" A1B2-C3D4-E5F6-7890 ") == CHAVE
    assert licensa_service._parse_chave("A1B2C3D4-E5F67890") == CHAVE
    assert licensa_service._parse_chave("A1B2-C3D4-E5F6-789") == ""
    assert licensa_service._parse_chave("A1B2-C3D4-E5F6-7890-ABCD") == ""
    assert licensa_service._parse_chave("NAO-EH-CHAVE-AQUI!!!") == ""
    assert licensa_service._parse_chave("") == ""
    assert licensa_service._parse_chave(None) == ""


def test_chave_inexistente_devolve_400(client, monkeypatch):
    _mock(monkeypatch, httpx.Response(403, json={
        "detail": "Chave de ativação não encontrada.",
        "codigo": "CHAVE_NAO_ENCONTRADA",
    }))
    resp = _ativar(client, CHAVE_INVALIDA)
    assert resp.status_code == 400, resp.text
    assert client.get("/v1/licenca").json()["data"]["status"] == "nao_ativada"


def test_licenca_vitalicia_ativa_sem_expiracao(client, monkeypatch):
    _mock(monkeypatch, _resposta_ok(expira_em=None))
    resp = _ativar(client)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["estado"] == "ativa"
    assert data["expira_em"] is None
    assert data["tolerancia_expira_em"] is None


def test_limite_de_ativacoes_devolve_409(client, monkeypatch):
    _mock(monkeypatch, httpx.Response(409, json={
        "detail": "Limite de ativações excedido.",
        "codigo": "LIMITE_ATIVACOES_EXCEDIDO",
    }))
    resp = _ativar(client)
    assert resp.status_code == 409, resp.text
    assert "limite" in resp.json()["detail"].lower()


# ------------------------------------------------------------- revalidação
def test_revalidacao_mantem_licenca_ativa(client, monkeypatch):
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "ativa"
    assert data["modo_leitura"] is False


def test_revogacao_volta_ao_modo_leitura(client, admin_token, monkeypatch):
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(403, json={
        "detail": "Licença revogada.",
        "codigo": "LICENCA_REVOGADA",
    }))
    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 423

    data = client.get("/v1/licenca").json()["data"]
    assert data["status"] == "revogada"
    assert data["estado"] == "revogada"
    assert data["modo_leitura"] is True

    resp = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Bloqueado", "tipo_pessoa": "pf"},
    )
    assert resp.status_code == 423


def test_bloqueio_entra_em_modo_leitura(client, monkeypatch):
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(403, json={
        "detail": "Licença bloqueada por inadimplência.",
        "codigo": "LICENCA_BLOQUEADA",
    }))
    assert client.post("/v1/licenca/renovar").status_code == 423

    data = client.get("/v1/licenca").json()["data"]
    assert data["status"] == "bloqueada"
    assert data["modo_leitura"] is True


def test_renovar_sem_ativacao_400(client):
    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 400


def test_renovar_sem_credencial_configurada_502(client, monkeypatch):
    monkeypatch.setattr(settings, "redgest_api_key", "")
    resp = _ativar(client)
    assert resp.status_code == 502, resp.text
    assert "credencial" in resp.json()["detail"].lower()


# ------------------------------------------- resiliência de rede (plano E1)
def test_ativacao_sem_rede_devolve_503(client, monkeypatch):
    """RedGest inacessível na ativação: 503 com mensagem clara, nunca 500 cru."""
    _mock_sem_rede(monkeypatch)
    resp = _ativar(client)
    assert resp.status_code == 503, resp.text
    assert "não foi possível falar com o servidor de licenças" in resp.json()[
        "detail"
    ].lower()


def test_timeout_na_revalidacao_nao_revoga(client, monkeypatch):
    """Cold start do RedGest não pode revogar a licença local."""
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock_sem_rede(monkeypatch, httpx.ReadTimeout("cold start do plano gratuito"))
    assert client.post("/v1/licenca/renovar").status_code == 503

    data = client.get("/v1/licenca").json()["data"]
    assert data["status"] == "ativa"
    assert data["modo_leitura"] is False


def test_backoff_crescente_e_saturado(monkeypatch):
    """1/5/15/60 min por falha consecutiva (doc §9.2); satura no último passo."""
    monkeypatch.setattr(settings, "licenca_backoff_segundos", "60,300,900,3600")
    monkeypatch.setattr(settings, "licenca_backoff_jitter_percentual", 0)
    assert (
        licensa_service._atraso_proximo_ciclo(0)
        == settings.licenca_refresh_intervalo_segundos
    )
    for falhas, segundos in ((1, 60), (2, 300), (3, 900), (4, 3600), (9, 3600)):
        assert licensa_service._atraso_proximo_ciclo(falhas) == segundos


def test_backoff_aplica_jitter_dentro_da_faixa(monkeypatch):
    """Doc §9.2: backoff exponencial **com jitter** (±20% por padrão)."""
    monkeypatch.setattr(settings, "licenca_backoff_segundos", "60,300,900,3600")
    monkeypatch.setattr(settings, "licenca_backoff_jitter_percentual", 20)
    valores = {licensa_service._atraso_proximo_ciclo(1) for _ in range(300)}
    assert valores <= set(range(48, 73)), sorted(valores)
    assert len(valores) > 1  # de fato varia entre ciclos


def test_backoff_com_config_invalida_usa_padrao(monkeypatch):
    monkeypatch.setattr(settings, "licenca_backoff_segundos", "abc,,x")
    assert settings.licenca_backoff == [60, 300, 900, 3600]


# ------------------------------------------------ limitação de taxa (429/5xx)
def test_429_vira_503_e_nao_revoga(client, monkeypatch):
    """Doc §8.3/§9.2: 429 é transitório, respeita o backoff e não revoga."""
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(429, text="too many requests"))
    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 503, resp.text

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "ativa"  # nunca revoga por 429
    assert "429" in (data["ultimo_erro"] or "")


def test_erro_5xx_vira_503_e_registra_diagnostico(client, monkeypatch):
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(502, text="bad gateway"))
    assert client.post("/v1/licenca/renovar").status_code == 503

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "ativa"
    assert "indisponível" in (data["ultimo_erro"] or "").lower()


def test_status_inesperado_404_vira_502_e_nao_revoga(client, monkeypatch):
    """404 (ex.: URL do RedGest com path duplicado) não pode revogar.

    Só uma recusa explícita do servidor revoga. Um status que o contrato não
    prevê é falha de integração: o cliente vê 502 e a licença local continua
    ativa — o oposto do que aconteceria se o 404 fosse lido como \"inválida\".
    """
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(404, json={"detail": "Not Found"}))
    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 502, resp.text
    assert "inesperada" in resp.json()["detail"].lower()

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "ativa"
    assert data["status"] == "ativa"


# -------------------------------- recusa dentro de um 200 (`valido: false`)
def test_recusa_200_revogada_entra_modo_leitura(client, monkeypatch):
    """Doc §8.2: a recusa também pode chegar em 200 com `valido: false`."""
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock(
        monkeypatch,
        httpx.Response(200, json={"valido": False, "motivo": "licenca_revogada"}),
    )
    assert client.post("/v1/licenca/renovar").status_code == 423

    data = client.get("/v1/licenca").json()["data"]
    assert data["status"] == "revogada"
    assert data["modo_leitura"] is True


def test_recusa_200_chave_invalida_devolve_400(client, monkeypatch):
    _mock(
        monkeypatch,
        httpx.Response(200, json={"valido": False, "motivo": "chave_invalida"}),
    )
    resp = _ativar(client, CHAVE_INVALIDA)
    assert resp.status_code == 400, resp.text
    assert client.get("/v1/licenca").json()["data"]["status"] == "nao_ativada"


def test_recusa_200_limite_devolve_409(client, monkeypatch):
    _mock(
        monkeypatch,
        httpx.Response(
            200, json={"valido": False, "motivo": "limite_ativacoes_excedido"}
        ),
    )
    resp = _ativar(client)
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------- fingerprint (doc §7)
def test_fingerprint_do_hardware_e_canonico(monkeypatch):
    """JSON canônico (chaves ordenadas) + SHA-256 hex minúsculo, estável."""
    monkeypatch.setattr(settings, "maquina_fingerprint", "")
    monkeypatch.setattr(
        licensa_service,
        "_consultar_hardware",
        lambda: {"placa_mae_serial": "B", "bios_uuid": "A"},
    )
    licensa_service._fingerprint_do_hardware.cache_clear()
    try:
        esperado = hashlib.sha256(
            b'{"bios_uuid":"A","placa_mae_serial":"B"}'
        ).hexdigest()
        obtido = licensa_service._fingerprint()
        assert obtido == esperado
        assert len(obtido) == 64
        assert obtido == licensa_service._fingerprint()  # determinístico
    finally:
        licensa_service._fingerprint_do_hardware.cache_clear()


def test_fingerprint_descarta_identificadores_genericos():
    """Placa/SMBIOS sem serial ('None', tudo zeros) não entra no fingerprint."""
    assert licensa_service._valor_util("None") == ""
    assert licensa_service._valor_util("  To Be Filled By O.E.M. ") == ""
    assert licensa_service._valor_util("00000000-0000-0000-0000-000000000000") == ""
    assert licensa_service._valor_util("  ") == ""
    assert licensa_service._valor_util("ABC-123") == "ABC-123"


def test_fingerprint_override_por_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "maquina_fingerprint", "ABC123")
    assert licensa_service._fingerprint() == "abc123"


def test_fingerprint_sem_hardware_usa_fallback_estavel(monkeypatch):
    """Sem hardware disponível, cai num fallback estável (sem hostname/MAC)."""
    monkeypatch.setattr(settings, "maquina_fingerprint", "")
    monkeypatch.setattr(licensa_service, "_consultar_hardware", lambda: {})
    monkeypatch.setattr("platform.machine", lambda: "AMD64")
    monkeypatch.setattr("platform.processor", lambda: "")
    licensa_service._fingerprint_do_hardware.cache_clear()
    try:
        esperado = hashlib.sha256(b'{"arquitetura":"AMD64"}').hexdigest()
        assert licensa_service._fingerprint() == esperado
    finally:
        licensa_service._fingerprint_do_hardware.cache_clear()


# ------------------------------------------------ cofre do SO (doc §9.4)
def test_chave_de_ativacao_e_guardada_no_cofre(client, monkeypatch):
    """O banco não guarda a chave em texto puro; o serviço a abre para revalidar."""
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    sessao = SessionLocal()
    try:
        lic = sessao.query(Licenca).first()
        guardada = lic.chave_ativacao
        em_claro = licensa_service._chave_em_claro(lic)
    finally:
        sessao.close()

    assert em_claro == CHAVE
    if cofre.disponivel():
        assert guardada.startswith(cofre.PREFIXO)
        assert CHAVE not in guardada


def test_revalidacao_envia_a_chave_em_claro(client, monkeypatch):
    """A revalidação manda a chave (não o blob do cofre) ao RedGest."""
    registro = _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    registro.clear()
    assert client.post("/v1/licenca/renovar").status_code == 200
    assert json.loads(registro[0].read())["chave_ativacao"] == CHAVE


def test_renovar_com_cofre_ilegivel_pede_reativacao(client, monkeypatch):
    """Banco restaurado de outro computador: blob ilegível → orienta reativar."""
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    sessao = SessionLocal()
    try:
        lic = sessao.query(Licenca).first()
        # Blob do cofre válido em Base64, mas que não abre nesta máquina/chave.
        lic.chave_ativacao = cofre.PREFIXO + "YWJjZGVm"
        sessao.commit()
    finally:
        sessao.close()
    licensa_service._abrir_chave.cache_clear()

    resp = client.post("/v1/licenca/renovar")
    assert resp.status_code == 400, resp.text
    assert "reative" in resp.json()["detail"].lower()
    assert client.get("/v1/licenca").json()["data"]["estado"] == "nao_ativada"


# ------------------------------- estados e tolerância offline (plano E2)
def test_ativacao_define_janela_de_tolerancia(client, monkeypatch):
    _mock(monkeypatch, _resposta_ok())
    resp = _ativar(client)
    assert resp.status_code == 200, resp.text

    data = resp.json()["data"]
    assert data["estado"] == "ativa"
    assert data["motivo"]
    janela = _parse(data["tolerancia_expira_em"]) - _parse(data["expira_em"])
    assert janela.total_seconds() == settings.licenca_tolerancia_horas * 3600


def test_vigencia_vencida_dentro_da_tolerancia_opera_normal(
    client, admin_token, monkeypatch
):
    """Queda do RedGest não bloqueia no instante do vencimento (tolerância ativa)."""
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        expira_em=agora - dt.timedelta(hours=1),
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
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        expira_em=agora - dt.timedelta(hours=73),
        tolerancia_expira_em=agora - dt.timedelta(hours=1),
    )

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "leitura"
    assert data["modo_leitura"] is True


def test_tolerancia_derivada_quando_coluna_nula(client, monkeypatch):
    """Bases antigas sem `tolerancia_expira_em`: deriva da vigência."""
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        expira_em=agora - dt.timedelta(hours=1),
        tolerancia_expira_em=None,
    )

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "tolerancia"
    assert data["modo_leitura"] is False
    assert data["tolerancia_expira_em"] is not None  # derivada da vigência


# ----------------------- cold start real + rollover (E6 do plano)
def test_cold_start_lento_conclui_sem_erro_visivel(client, monkeypatch):
    """Aceite 1: RedGest "frio" responde devagar, mas dentro do timeout -> 200.

    O `MockTransport` do httpx nao aplica timeout ao handler; aqui um socket real
    dorme antes de responder, provando que `licenca_timeout_segundos` e de fato
    aplicado a requisicao e que a lentidao nao vira erro nem revogacao.
    """
    with _RedGestReal(atraso=0.4) as redgest:
        monkeypatch.setattr(settings, "redgest_url", redgest.url)
        monkeypatch.setattr(settings, "licenca_timeout_segundos", 10)
        resp = _ativar(client)

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["estado"] == "ativa"
    assert data["ultimo_erro"] is None
    assert len(redgest.requisicoes) == 1
    assert redgest.requisicoes[0]["caminho"] == CAMINHO


def test_cold_start_estoura_timeout_real_e_recupera(client, monkeypatch):
    """Aceite 1/2: atraso real acima do timeout -> 503, sem revogar; depois volta.

    Prova o par: (a) o timeout configurado e o que interrompe a chamada (erro de
    transporte real, nao um mock) e (b) quando o RedGest responde dentro do
    prazo, a revalidacao volta a `ativa` e limpa o diagnostico.
    """
    with _RedGestReal(atraso=0.0) as redgest:
        monkeypatch.setattr(settings, "redgest_url", redgest.url)
        monkeypatch.setattr(settings, "licenca_timeout_segundos", 10)
        assert _ativar(client).status_code == 200

        redgest.atraso = 1.5  # RedGest "frio": 1,5 s com timeout de 0,2 s
        monkeypatch.setattr(settings, "licenca_timeout_segundos", 0.2)
        assert client.post("/v1/licenca/renovar").status_code == 503

        data = client.get("/v1/licenca").json()["data"]
        assert data["estado"] == "ativa"  # indisponibilidade nunca revoga
        assert data["modo_leitura"] is False
        assert "Timeout" in (data["ultimo_erro"] or "")

        redgest.atraso = 0.0  # respondeu dentro do prazo: recupera sozinho
        monkeypatch.setattr(settings, "licenca_timeout_segundos", 10)
        assert client.post("/v1/licenca/renovar").status_code == 200

        data = client.get("/v1/licenca").json()["data"]
        assert data["estado"] == "ativa"
        assert data["ultimo_erro"] is None


def test_revalidacao_renova_a_vigencia_e_reativa(client, monkeypatch):
    """Rollover da vigencia (o Contrato C nao tem token para renovar).

    Em tolerancia, uma revalidacao que traz `expira_em` novo substitui o local
    (o RedGest e a fonte da verdade): a instalacao volta a `ativa` e a janela de
    tolerancia e recalculada a partir da nova vigencia.
    """
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    agora = licensa_service._agora()
    _ajustar_licenca(
        expira_em=agora - dt.timedelta(hours=1),
        tolerancia_expira_em=agora + dt.timedelta(hours=71),
    )
    assert client.get("/v1/licenca").json()["data"]["estado"] == "tolerancia"

    nova = agora + dt.timedelta(days=365)
    _mock(monkeypatch, _resposta_ok(expira_em=_iso(nova), primeira_ativacao=False))
    assert client.post("/v1/licenca/renovar").status_code == 200

    data = client.get("/v1/licenca").json()["data"]
    assert data["estado"] == "ativa"
    assert data["modo_leitura"] is False
    assert _parse(data["expira_em"]) == nova
    assert _parse(data["tolerancia_expira_em"]) == nova + dt.timedelta(
        hours=settings.licenca_tolerancia_horas
    )


def test_revalidacao_de_licenca_vitalicia_continua_vitalicia(client, monkeypatch):
    """`expira_em: null` (vitalicia) atravessa a revalidacao sem criar tolerancia."""
    _mock(monkeypatch, _resposta_ok(expira_em=None))
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, _resposta_ok(expira_em=None, primeira_ativacao=False))
    assert client.post("/v1/licenca/renovar").status_code == 200

    data = client.get("/v1/licenca").json()["data"]
    assert data["expira_em"] is None
    assert data["tolerancia_expira_em"] is None
    assert data["estado"] == "ativa"
    assert data["modo_leitura"] is False


def test_falha_de_revalidacao_registra_diagnostico(client, monkeypatch):
    """Falha de rede grava `ultima_tentativa_em`/`ultimo_erro` para a UI."""
    _mock(monkeypatch, _resposta_ok())
    assert _ativar(client).status_code == 200

    _mock_sem_rede(monkeypatch)
    assert client.post("/v1/licenca/renovar").status_code == 503

    data = client.get("/v1/licenca").json()["data"]
    assert data["ultima_tentativa_em"] is not None
    assert "inacessível" in (data["ultimo_erro"] or "")
    assert data["estado"] == "ativa"  # a vigência local ainda vale
