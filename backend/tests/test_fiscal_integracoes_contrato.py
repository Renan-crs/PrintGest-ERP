"""Contrato Fiscal/Integrações — cliente desktop ↔ backend.

Regressiones: envelope de listagem de integrações, gateway configurado pelo
banco (sem `.env`), sanitização de segredos em mensagens e RBAC/contadores.
"""

from app.core.config import settings
from app.db import SessionLocal
from app.models.enums import StatusFiscal, TipoIntegracao
from app.services import fiscal_service
from app.services.fiscal_gateway import FiscalGateway
from tests.conftest import auth


def test_lista_integracoes_tem_meta(client, admin_token):
    r = client.get("/v1/config/integracoes", headers=auth(client, admin_token))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert "data" in corpo and "meta" in corpo
    assert corpo["meta"]["total"] == corpo["total"] == len(corpo["data"])


def test_gateway_pode_ser_configurado_somente_pela_integracao(
    client, admin_token, monkeypatch
):
    monkeypatch.setattr(settings, "fiscal_gateway_url", "")
    monkeypatch.setattr(FiscalGateway, "health", lambda self: True)
    fiscal_service.invalidar_cache_disponibilidade()

    from app.models.integracao import Integracao, IntegracaoEvento

    db_limpeza = SessionLocal()
    try:
        db_limpeza.query(IntegracaoEvento).delete()
        db_limpeza.query(Integracao).delete()
        db_limpeza.commit()
    finally:
        db_limpeza.close()

    r = client.post(
        "/v1/config/integracoes",
        headers=auth(client, admin_token),
        json={
            "tipo": TipoIntegracao.FISCAL.value,
            "nome": "Gateway Fiscal",
            "provedor": "Teste",
            "base_url": "https://gateway.test/v2",
        },
    )
    assert r.status_code == 201, r.text
    integracao_id = r.json()["data"]["id"]

    from app.models.integracao import Integracao, IntegracaoEvento

    db = SessionLocal()
    try:
        info = fiscal_service.gateway_info(db, filial_id=1)
        # Limpa para não contaminar os testes de gateway sem integração.
        db.query(IntegracaoEvento).filter(
            IntegracaoEvento.integracao_id == integracao_id
        ).delete()
        db.query(Integracao).filter(Integracao.id == integracao_id).delete()
        db.commit()
    finally:
        db.close()
    assert info["gateway_configurado"] is True
    assert info["gateway_url"] == "https://gateway.test/v2"

    # Sem integração e sem .env → mensagem orienta as duas opções.
    fiscal_service.invalidar_cache_disponibilidade()
    assert "Integrações" in fiscal_service.gateway_info(None, 1)["mensagem"]


def test_sanitizacao_cobre_chaves_e_mensagens_livres():
    from app.services.fiscal_service import _mascarar_texto, _sanitizar

    texto = "erro: Authorization: Bearer abc123XYZ token=def456 chave_privada=segredo"
    limpo = _mascarar_texto(texto)
    for segredo in ("abc123XYZ", "def456", "segredo"):
        assert segredo not in limpo

    dados = {
        "access_token": "abc123",
        "private_key_pem": "PEM",
        "api_key": "xyz",
        "seguro": "valor",
    }
    saida = _sanitizar(dados)
    assert saida["access_token"] == "***"
    assert saida["private_key_pem"] == "***"
    assert saida["api_key"] == "***"
    assert saida["seguro"] == "valor"


def test_contingenciado_conta_como_pendente():
    assert StatusFiscal.CONTINGENCIADO in fiscal_service._STATUS_PENDENTES
