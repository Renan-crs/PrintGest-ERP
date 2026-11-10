"""Contrato B do RedGest (`Licenca` v4.0, `/api/v1/licencas/`) — matriz §14.1.

Cobre os itens obrigatórios do manual de integração contra um RedGest falso
(`httpx.MockTransport`), com foco no que o adaptador faz de diferente do
Contrato C: handshake com `Idempotency-Key`, credenciais M2M no cofre, rotação
do `client_secret`, `hardware_profile`, `grace_deadline` e o mapeamento de
`motivo` para o estado local. A suíte é hermética: nenhum processo externo.
"""

import datetime as dt
import json
import uuid

import httpx
import pytest

from app.core import cofre, cofre_maquina
from app.core.config import settings
from app.services import licensa_contrato_b as contrato_b
from app.services import licensa_service
from tests.conftest import auth

CNPJ = "12345678000199"
CODIGO = "TESTE-GRAFICA-2026"
CLIENT_ID = "grafica_12345678000199"
CLIENT_SECRET = "s3gr3d0-inicial"
FINGERPRINT_FIXO = "b" * 64
DIA = 24 * 3600


@pytest.fixture(autouse=True)
def _contrato_b(client, monkeypatch, tmp_path):
    """Roda DEPOIS do conftest: limpa a licença e liga o Contrato B."""
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    monkeypatch.setattr(settings, "redgest_contrato", "b")
    monkeypatch.setattr(settings, "licenca_desabilitada", False)
    monkeypatch.setattr(settings, "maquina_fingerprint", FINGERPRINT_FIXO)
    # Cópia de recuperação isolada por teste (nunca toca o arquivo real).
    monkeypatch.setattr(
        settings, "cofre_licenca_arquivo", str(tmp_path / "licenca.dat")
    )
    cofre_maquina.limpar()

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
    cofre_maquina.limpar()


# ------------------------------------------------------------------- helpers
def _iso(quando: dt.datetime) -> str:
    return quando.isoformat()


def _grace(dias: float = 3) -> str:
    return _iso(licensa_service._agora() + dt.timedelta(days=dias))


def _resposta_ativacao(**overrides) -> httpx.Response:
    corpo = {
        "id": CODIGO,
        "cliente_id": CNPJ,
        "sistema_codigo": "printgest",
        "status": "ATIVA",
        "entitlements": {"cnpj_vinculado": CNPJ, "max_estacoes": 5},
        "data_inicio": _iso(licensa_service._agora()),
        "data_fim": _iso(licensa_service._agora() + dt.timedelta(days=30)),
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "modo": "hardware_bound",
    }
    corpo.update(overrides)
    return httpx.Response(200, json={"data": corpo})


def _resposta_validacao(**overrides) -> httpx.Response:
    corpo = {
        "licenca_id": CODIGO,
        "valida": True,
        "status": "ATIVA",
        "sistema_codigo": "printgest",
        "cliente_id": CNPJ,
        "entitlements": {"cnpj_vinculado": CNPJ, "max_estacoes": 5},
        "dias_restantes": 341,
        "motivo": None,
        "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.assinado",
        "token_expira_em": _iso(licensa_service._agora() + dt.timedelta(minutes=15)),
        "grace_deadline": _grace(),
        "modo_leitura": False,
        "expires_in": 900,
        "client_id": CLIENT_ID,
        "client_secret": "s3gr3d0-rotacionado",
    }
    corpo.update(overrides)
    return httpx.Response(200, json={"data": corpo})


def _mock(monkeypatch, resposta):
    """Injeta o RedGest falso preservando base_url/headers/timeout reais."""
    registro: list[httpx.Request] = []
    transporte = httpx.MockTransport(
        lambda request: (
            registro.append(request),
            resposta(request) if callable(resposta) else resposta,
        )[1]
    )
    original = licensa_service._cliente_com_idempotencia

    def cliente(chave_idempotencia: str) -> httpx.Client:
        return original(chave_idempotencia).__class__(
            base_url="http://redgest.local",
            timeout=settings.licenca_timeout_segundos,
            transport=transporte,
            headers={"Idempotency-Key": chave_idempotencia},
        )

    monkeypatch.setattr(licensa_service, "_cliente_com_idempotencia", cliente)
    return registro


def _ativar(client, cnpj: str = CNPJ, codigo: str = CODIGO):
    return client.post(
        "/v1/licenca/ativar", json={"cnpj": cnpj, "codigo_licenca": codigo}
    )


def _licenca(campos: dict | None = None):
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    sessao = SessionLocal()
    try:
        lic = sessao.query(Licenca).first()
        if campos and lic is not None:
            return {campo: getattr(lic, campo) for campo in campos}
        return lic
    finally:
        sessao.close()


def _ajustar_licenca(**campos):
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


# ------------------------------------------------- ativação (itens 1, 2, 3)
def test_ativacao_guarda_credenciais_no_cofre(client, monkeypatch):
    registro = _mock(monkeypatch, _resposta_ativacao())

    resp = _ativar(client)

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["contrato"] == "b"
    assert data["estado"] == "ativa"
    assert data["modo_leitura"] is False

    request = registro[-1]
    assert request.url.path == f"/api/v1/licencas/{CODIGO}/ativar/"
    assert request.headers["Idempotency-Key"]  # §14.1 item 6: obrigatório
    corpo = json.loads(request.read())
    assert corpo["cnpj"] == CNPJ
    assert corpo["codigo_licenca"] == CODIGO
    assert corpo["hardware_profile"]  # §11.4: perfil sempre enviado

    lic = _licenca()
    if cofre.disponivel():
        # doc §9.4: nunca em texto puro (no Linux sem DPAPI o cofre cai em
        # texto puro por design — ver cofre.disponivel).
        assert lic.client_secret != CLIENT_SECRET
        assert CLIENT_SECRET not in (lic.client_secret or "")
    assert cofre.revelar(lic.client_secret) == f"{CLIENT_ID}|{CLIENT_SECRET}"
    assert lic.client_id is None  # metade do par não fica em coluna aberta
    assert cofre.revelar(lic.chave_ativacao) == CODIGO


def test_ativacao_aceita_cnpj_com_mascara(client, monkeypatch):
    registro = _mock(monkeypatch, _resposta_ativacao())

    resp = _ativar(client, cnpj="12.345.678/0001-99")

    assert resp.status_code == 200, resp.text
    assert json.loads(registro[-1].read())["cnpj"] == CNPJ


def test_ativacao_cnpj_invalido_nao_chama_redgest(client, monkeypatch):
    registro = _mock(monkeypatch, _resposta_ativacao())

    resp = _ativar(client, cnpj="123")

    assert resp.status_code == 400
    assert "CNPJ inválido" in resp.json()["detail"]
    assert registro == []


def test_ativacao_codigo_vazio_nao_chama_redgest(client, monkeypatch):
    registro = _mock(monkeypatch, _resposta_ativacao())

    resp = _ativar(client, codigo="  ")

    assert resp.status_code == 400
    assert "código da licença" in resp.json()["detail"]
    assert registro == []


def test_ativacao_recusada_repassa_mensagem(client, monkeypatch):
    _mock(
        monkeypatch,
        httpx.Response(
            400,
            json={
                "detail": "Licença expirada, sem reativação.",
                "codigo": "LICENCA_EXPIRADA",
            },
        ),
    )

    resp = _ativar(client)

    assert resp.status_code == 400
    assert "expirada" in resp.json()["detail"]
    assert _licenca() is None


# --------------------------- recuperação na mesma máquina (reinstalação)
def _apagar_licenca_local() -> None:
    """Simula reinstalação/recriação do banco: a linha local deixa de existir."""
    from app.db import SessionLocal
    from app.models.licenca import Licenca

    sessao = SessionLocal()
    try:
        sessao.query(Licenca).delete()
        sessao.commit()
    finally:
        sessao.close()


def test_ativacao_grava_copia_de_recuperacao_na_maquina(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())

    assert _ativar(client).status_code == 200

    material = cofre_maquina.ler()
    assert material["cnpj"] == CNPJ
    assert material["codigo"] == CODIGO
    assert material["licenca_id"] == CODIGO
    assert material["client_id"] == CLIENT_ID
    assert material["client_secret"] == CLIENT_SECRET
    # nunca em texto puro no arquivo (quando o DPAPI está disponível)
    if cofre.disponivel():
        assert CLIENT_SECRET not in cofre_maquina.caminho().read_text(encoding="utf-8")


def test_reinstalacao_recupera_pelo_cofre_local_sem_novo_handshake(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200
    _apagar_licenca_local()

    registro = _mock(monkeypatch, _resposta_validacao())
    resp = _ativar(client)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["estado"] == "ativa"
    assert len(registro) == 1  # nenhum novo /ativar: só /validar
    assert registro[0].url.path == f"/api/v1/licencas/{CODIGO}/validar/"
    corpo = json.loads(registro[0].read())
    assert corpo["client_id"] == CLIENT_ID
    assert corpo["client_secret"] == CLIENT_SECRET
    assert corpo["hardware_profile"]

    lic = _licenca()
    assert lic is not None
    assert cofre.revelar(lic.chave_ativacao) == CODIGO
    # O /validar rotacionou o secret: a cópia local acompanha.
    assert cofre_maquina.ler()["client_secret"] == "s3gr3d0-rotacionado"


def test_renovar_reconstroi_linha_perdida_pelo_cofre_local(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200
    _apagar_licenca_local()

    registro = _mock(monkeypatch, _resposta_validacao())
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 200, resp.text
    assert registro[-1].url.path == f"/api/v1/licencas/{CODIGO}/validar/"
    assert _licenca() is not None


def test_banco_de_outra_maquina_usa_copia_local(client, monkeypatch):
    """Blob DPAPI do banco ilegível, mas a cópia desta máquina recupera."""
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200
    _ajustar_licenca(client_secret="dpapi:v1:@@@ilegivel@@@")

    registro = _mock(monkeypatch, _resposta_validacao())
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 200, resp.text
    corpo = json.loads(registro[-1].read())
    assert corpo["client_secret"] == CLIENT_SECRET  # veio da cópia local
    assert cofre.revelar(_licenca().client_secret) == f"{CLIENT_ID}|s3gr3d0-rotacionado"


def test_ativar_ja_ativada_sem_copia_local_orienta_reset(client, monkeypatch):
    cofre_maquina.limpar()
    _mock(
        monkeypatch,
        httpx.Response(
            409,
            json={
                "detail": (
                    "Licença já possui ativação ativa. Solicite ao suporte o "
                    "reset das credenciais M2M antes de reativar"
                ),
                "codigo": "LICENCA_JA_ATIVADA",
            },
        ),
    )

    resp = _ativar(client)

    assert resp.status_code == 409
    detalhe = resp.json()["detail"]
    assert CODIGO in detalhe
    assert "reset" in detalhe.lower()
    assert "M2M" in detalhe
    assert _licenca() is None


# -------------------------------------------- revalidação (itens 4, 5, 7, 9)
def test_renovar_rotaciona_credenciais_e_mantem_ativa(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    registro = _mock(monkeypatch, _resposta_validacao())
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["estado"] == "ativa"
    request = registro[-1]
    assert request.url.path == f"/api/v1/licencas/{CODIGO}/validar/"
    assert request.headers["Idempotency-Key"]
    corpo = json.loads(request.read())
    assert corpo["client_id"] == CLIENT_ID
    assert corpo["client_secret"] == CLIENT_SECRET
    assert corpo["hardware_profile"]

    # §7.3: o `/validar` rotaciona o segredo; o valor novo vai para o cofre.
    assert cofre.revelar(_licenca().client_secret) == f"{CLIENT_ID}|s3gr3d0-rotacionado"


def test_renovar_idempotency_key_e_uuid_por_operacao(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    registro = _mock(monkeypatch, _resposta_validacao())
    client.post("/v1/licenca/renovar")
    client.post("/v1/licenca/renovar")

    chaves = [r.headers["Idempotency-Key"] for r in registro]
    for chave in chaves:
        uuid.UUID(chave)  # uuid-v4 válido, ≤128 chars (§10.1)
    assert len(set(chaves)) == 2  # uma chave por operação lógica


def test_erro_403_reconquista_ativacao_sem_revogar(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(403, json={"detail": "Credenciais inválidas."}))
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 400
    assert "Reative a licença" in resp.json()["detail"]
    assert client.get("/v1/licenca").json()["data"]["estado"] == "ativa"


def test_renovar_sem_credenciais_pede_reativacao(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200
    _ajustar_licenca(client_secret=None)
    cofre_maquina.limpar()  # sem cópia de recuperação nesta máquina

    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 400
    assert "Reative a licença" in resp.json()["detail"]


# ------------------------------------------------ recusas (itens 8, 9, 18, 20)
@pytest.mark.parametrize(
    ("motivo", "esperado"),
    [
        ("licenca_revogada", "revogada"),
        ("licenca_suspensa", "bloqueada"),
        ("licenca_bloqueada", "bloqueada"),
    ],
)
def test_motivos_de_recusa_viram_modo_leitura(client, monkeypatch, motivo, esperado):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, _resposta_validacao(valida=False, motivo=motivo))
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 423
    situacao = client.get("/v1/licenca").json()["data"]
    assert situacao["status"] == esperado
    assert situacao["modo_leitura"] is True
    assert situacao["motivo"]  # mensagem específica, não a genérica


def test_hardware_divergente_aponta_rebind(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, _resposta_validacao(valida=False, motivo="hardware_divergente"))
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 423
    assert "rebind" in resp.json()["detail"]
    assert "rebind" in client.get("/v1/licenca").json()["data"]["motivo"]


def test_vigencia_vencida_dentro_do_grace_opera_normal(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    grace = _grace()
    _mock(
        monkeypatch,
        _resposta_validacao(
            valida=False, motivo="licenca_expirada", grace_deadline=grace
        ),
    )
    resp = client.post("/v1/licenca/renovar")

    # §12: `data_fim` venceu mas ainda dentro do `grace_deadline` -> tolerância.
    assert resp.status_code == 200, resp.text
    situacao = resp.json()["data"]
    assert situacao["estado"] == "tolerancia"
    assert situacao["modo_leitura"] is False
    assert licensa_service._parse_dt(
        situacao["tolerancia_expira_em"]
    ) == licensa_service._parse_dt(grace)


def test_grace_esgotado_entra_em_modo_leitura(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    passado = _iso(licensa_service._agora() - dt.timedelta(hours=1))
    _mock(
        monkeypatch,
        _resposta_validacao(
            valida=False, motivo="licenca_expirada", grace_deadline=passado
        ),
    )
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 423
    situacao = client.get("/v1/licenca").json()["data"]
    assert situacao["estado"] == "leitura"
    assert situacao["modo_leitura"] is True


# ----------------------------------------------------- resiliência (item 22)
def test_falha_de_rede_devolve_503_sem_revogar(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    def sem_rede(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rota para o RedGest")

    _mock(monkeypatch, sem_rede)
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 503
    situacao = client.get("/v1/licenca").json()["data"]
    assert situacao["estado"] == "ativa"
    assert situacao["modo_leitura"] is False
    assert "inacessível" in (situacao["ultimo_erro"] or "") or situacao["ultimo_erro"]


def test_429_devolve_503_sem_revogar(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(429, json={"detail": "rate limit"}))
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 503
    assert client.get("/v1/licenca").json()["data"]["estado"] == "ativa"


def test_five_hundred_devolve_503_sem_revogar(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    _mock(monkeypatch, httpx.Response(502, text="bad gateway"))
    resp = client.post("/v1/licenca/renovar")

    assert resp.status_code == 503
    assert client.get("/v1/licenca").json()["data"]["modo_leitura"] is False


# ------------------------------------------------------------------ cadeado
def test_contrato_c_intacto_com_a_flag_desligada(client, monkeypatch):
    """Sem a flag, `ativar` exige a chave de produto (Contrato C)."""
    monkeypatch.setattr(settings, "redgest_contrato", "c")
    monkeypatch.setattr(settings, "redgest_api_key", "")

    resp = client.post(
        "/v1/licenca/ativar", json={"cnpj": CNPJ, "codigo_licenca": CODIGO}
    )

    assert resp.status_code == 400
    assert "Chave de ativação inválida" in resp.json()["detail"]


def test_bloqueio_operacional_impede_escrita_e_leitura_permite(
    client, admin_token, monkeypatch
):
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200
    assert (
        client.post(
            "/v1/clientes",
            headers=auth(client, admin_token),
            json={"nome_razao": "Ainda liberado", "tipo_pessoa": "pf"},
        ).status_code
        == 200
    )

    _mock(monkeypatch, _resposta_validacao(valida=False, motivo="licenca_revogada"))
    client.post("/v1/licenca/renovar")

    bloqueado = client.post(
        "/v1/clientes",
        headers=auth(client, admin_token),
        json={"nome_razao": "Revogado", "tipo_pessoa": "pf"},
    )
    assert bloqueado.status_code == 423
    assert (
        client.get("/v1/clientes", headers=auth(client, admin_token)).status_code == 200
    )
    assert client.get("/v1/licenca").status_code == 200


# ---------------------------------------------------------- helpers internos
def test_resposta_sem_json_vira_502(client, monkeypatch):
    _mock(monkeypatch, httpx.Response(200, text="<html>erro</html>"))

    resp = _ativar(client)

    assert resp.status_code == 502
    assert "não-JSON" in resp.json()["detail"]


def test_entitlements_do_redgest_ficam_guardados(client, monkeypatch):
    _mock(monkeypatch, _resposta_ativacao())
    _ativar(client)

    lic = _licenca()
    assert lic.entitlements["redgest"]["max_estacoes"] == 5
    assert lic.entitlements["cnpj"] == CNPJ
    assert lic.entitlements["contrato"] == "b"


# --- M0 (PRD v3.0 §2): módulos do plano chegam pelo RedGest -----------------------


def test_modulos_do_plano_sao_persistidos_e_publicados(client, monkeypatch):
    """Com `modulos` no payload: topo do entitlements + `MODULOS_HABILITADOS`."""
    modulos = ["cadastros", "movimento", "caixa", "projetos", "fiscal"]
    _mock(
        monkeypatch,
        _resposta_ativacao(
            entitlements={
                "cnpj_vinculado": CNPJ,
                "max_estacoes": 5,
                "modulos": modulos,
            },
        ),
    )
    _ativar(client)

    lic = _licenca()
    assert lic.entitlements["modulos"] == sorted(modulos)
    assert licensa_service.MODULOS_HABILITADOS == set(modulos)
    # o payload original segue guardado para proveniência
    assert lic.entitlements["redgest"]["modulos"] == modulos


def test_payload_sem_modulos_apaga_o_valor_anterior(client, monkeypatch):
    """O payload é autoritativo: sem `modulos`, nada libera (regra do PRD)."""
    modulos = ["cadastros", "movimento"]
    _mock(
        monkeypatch,
        _resposta_ativacao(
            entitlements={
                "cnpj_vinculado": CNPJ,
                "max_estacoes": 5,
                "modulos": modulos,
            },
        ),
    )
    _ativar(client)
    assert "modulos" in _licenca().entitlements

    # revalidação SEM a lista: a chave some e o conjunto zera.
    _mock(
        monkeypatch,
        _resposta_validacao(
            entitlements={"cnpj_vinculado": CNPJ, "max_estacoes": 5},
        ),
    )
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        contrato_b.revalidar(db)
    finally:
        db.close()
    lic = _licenca()
    assert "modulos" not in lic.entitlements
    assert licensa_service.MODULOS_HABILITADOS == set()


def test_perfil_de_hardware_traduz_chaves_do_manual(monkeypatch):
    monkeypatch.setattr(
        licensa_service,
        "_consultar_hardware",
        lambda: {
            "bios_uuid": "BIOS-1",
            "cpu_id": "CPU-1",
            "placa_mae_serial": "PLACA-1",
            "disco_serial": "DISCO-1",
        },
    )

    assert contrato_b._perfil_hardware() == {
        "bios_uuid": "BIOS-1",
        "cpu": "CPU-1",
        "placa_mae": "PLACA-1",
        "disco_serial": "DISCO-1",
    }


def test_perfil_de_hardware_tem_fallback_estavel(monkeypatch):
    monkeypatch.setattr(licensa_service, "_consultar_hardware", dict)

    perfil = contrato_b._perfil_hardware()

    assert perfil  # não vazio: o RedGest exige o perfil no hardware_bound
    assert "hostname" not in perfil  # doc §7: nunca hostname/MAC


# ----------------------------------- substituição de licença (bug: continuidade)


def test_ativar_licenca_nova_substitui_revogada_sem_reusar_instancia_antiga(
    client, monkeypatch
):
    """Licença revogada + nova emitida (mesmo código, outra instância): `ativar`
    deve fazer o handshake da licença nova, nunca `/validar` na instância
    revogada antiga. Antes do fix, steps 1/2 reutilizavam as credenciais/ID da
    instância antiga e o sistema tratava a licença nova como continuidade da
    antiga (revogada)."""
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    # Simula estado local pós-revogação da instância antiga (ID distinto do novo).
    lic = _licenca()
    ent = dict(lic.entitlements or {})
    ent["licenca_id"] = "ANTIGA"
    _ajustar_licenca(
        status=licensa_service.STATUS_REVOGADA,
        entitlements=ent,
        ultimo_erro="[RedGest] licença revogada",
    )
    licensa_service.ESTADO["modo_leitura"] = True

    def roteado(request):
        if "/ativar/" in request.url.path:
            # Handshake da licença nova: instância diferente, mesmas credenciais
            # de exemplo (o importante é o novo `id`/identidade).
            return _resposta_ativacao(
                id="NOVA", licenca_id="NOVA", client_secret="segredo-novo"
            )
        if "/validar/" in request.url.path:
            # Não deve acontecer: provaria reuso da instância antiga.
            return _resposta_validacao(
                valida=False, motivo="licenca_revogada", licenca_id="ANTIGA"
            )
        return httpx.Response(404, json={"detail": "inesperado"})

    registro = _mock(monkeypatch, roteado)
    resp = _ativar(client)

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["estado"] == "ativa"
    assert data["modo_leitura"] is False
    # Foi ao handshake da licença nova, não ao /validar da instância antiga.
    assert any("/ativar/" in r.url.path for r in registro)
    assert not any("/validar/" in r.url.path for r in registro)
    lic_nova = _licenca()
    assert lic_nova.status == licensa_service.STATUS_ATIVA
    assert (lic_nova.entitlements or {}).get("licenca_id") == "NOVA"
    assert cofre.revelar(lic_nova.chave_ativacao) == CODIGO


def test_ativar_licenca_nova_com_codigo_diferente_substitui_revogada(
    client, monkeypatch
):
    """CNPJ igual, código DIFERENTE (licença nova emitida): mesmo com a local
    revogada, o handshake da nova deve ocorrer e a identidade antiga não pode
    permanecer."""
    _mock(monkeypatch, _resposta_ativacao())
    assert _ativar(client).status_code == 200

    lic = _licenca()
    ent = dict(lic.entitlements or {})
    ent["licenca_id"] = "ANTIGA"
    _ajustar_licenca(status=licensa_service.STATUS_REVOGADA, entitlements=ent)
    licensa_service.ESTADO["modo_leitura"] = True

    NOVO_CODIGO = "NOVA-LICENCA-2026"

    def roteado(request):
        if (
            f"/ativar/{NOVO_CODIGO}" in request.url.path
            or "/ativar/" in request.url.path
        ):
            return _resposta_ativacao(id=NOVO_CODIGO, licenca_id=NOVO_CODIGO)
        if "/validar/" in request.url.path:
            return _resposta_validacao(valida=False, motivo="licenca_revogada")
        return httpx.Response(404, json={"detail": "inesperado"})

    registro = _mock(monkeypatch, roteado)
    resp = _ativar(client, codigo=NOVO_CODIGO)

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["estado"] == "ativa"
    assert any("/ativar/" in r.url.path for r in registro)
    assert not any("/validar/" in r.url.path for r in registro)
    assert (_licenca().entitlements or {}).get("licenca_id") == NOVO_CODIGO
    assert cofre.revelar(_licenca().chave_ativacao) == NOVO_CODIGO
