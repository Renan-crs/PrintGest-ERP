"""Gating de módulos por plano (PRD v3.0 §2, M0): rota sem módulo → 403.

Cobre o mapa rota→módulo, a regra "entitlements ausente/malformado não libera
nenhum módulo" e o middleware de ponta a ponta com a flag armada — além do
comportamento padrão (flag desligada = nada muda, o piloto segue até o RedGest
emitir `modulos`).
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import gating, licensa_service

client = TestClient(app)


# ------------------------------------------------------------ mapa de rotas


@pytest.mark.parametrize(
    "caminho,esperado",
    [
        ("/v1/financeiro/caixa/atual", "caixa"),
        ("/v1/financeiro/caixa/7/fechar", "caixa"),
        ("/v1/financeiro/contas-receber", "caixa"),
        ("/v1/financeiro/contas-pagar", "financeiro"),
        ("/v1/financeiro/plano-contas", "financeiro"),
        ("/v1/clientes", "cadastros"),
        ("/v1/produtos", "cadastros"),
        ("/v1/os", "movimento"),
        ("/v1/vendas", "movimento"),
        ("/v1/projetos/quadro/1", "projetos"),
        ("/v1/fiscal/documentos", "fiscal"),
        ("/v1/config/empresa", "configuracoes"),
        ("/v1/usuarios", "configuracoes"),
        # De todos os planos (operacional/interno) — fora do mapa:
        ("/v1/dashboard/resumo", None),
        ("/v1/auth/login", None),
        ("/v1/licenca", None),
        ("/health", None),
    ],
)
def test_modulo_da_rota(caminho, esperado):
    assert gating.modulo_da_rota(caminho) == esperado


# ------------------------------------------- entitlements → módulos habilitados


@pytest.mark.parametrize(
    "entitlements,esperado",
    [
        (
            {"modulos": ["cadastros", "caixa", "movimento"]},
            {"cadastros", "caixa", "movimento"},
        ),
        ({"modulos": []}, set()),
        ({"modulos": "todas"}, set()),  # string: malformado
        ({"modulos": {"a": 1}}, set()),  # dict: malformado
        ({"modulos": [1, 2, None]}, set()),  # itens não-string: nada vira módulo
        ({"outra": "coisa"}, set()),  # sem a chave
        (None, set()),  # sem entitlements
    ],
)
def test_modulos_do_entitlements_malformado_nao_libera_nada(entitlements, esperado):
    assert licensa_service._modulos_do_entitlements(entitlements) == esperado


def test_recalcular_estado_alimenta_modulos_habilitados(monkeypatch):
    """O recálculo da licença publica o conjunto no módulo (fonte do middleware)."""
    monkeypatch.setattr(
        licensa_service, "_estado", lambda lic: licensa_service.ESTADO_ATIVA
    )
    try:

        class LicencaFalsa:
            entitlements: ClassVar[dict] = {"modulos": ["projetos", "fiscal"]}

        licensa_service._recalcular_estado(LicencaFalsa())
        assert licensa_service.MODULOS_HABILITADOS == {"projetos", "fiscal"}

        class SemLicenca:
            entitlements = None

        licensa_service._recalcular_estado(SemLicenca())
        assert licensa_service.MODULOS_HABILITADOS == set()
    finally:
        licensa_service._recalcular_estado(None)


# -------------------------------------------------------- middleware (403)


def _armar(monkeypatch, modulos: set[str]):
    monkeypatch.setattr(settings, "gating_modulos", True)
    monkeypatch.setattr(licensa_service, "MODULOS_HABILITADOS", set(modulos))


def test_modulo_habilitado_passa_e_bloqueado_responde_403(
    client, admin_token, monkeypatch
):
    _armar(
        monkeypatch,
        {"cadastros", "caixa", "movimento", "configuracoes", "estoque", "agendamento"},
    )
    cabecalho = {"Authorization": f"Bearer {admin_token}"}

    liberado = client.get("/v1/produtos", headers=cabecalho)
    assert liberado.status_code != 403
    assert "MODULO_BLOQUEADO" not in liberado.text

    bloqueado = client.get("/v1/projetos", headers=cabecalho)
    assert bloqueado.status_code == 403
    corpo = bloqueado.json()
    assert corpo["codigo"] == "MODULO_BLOQUEADO"
    assert corpo["modulo"] == "projetos"
    assert "Projetos" in corpo["detail"]


def test_entitlements_vazio_nao_libera_nenhum_modulo(client, admin_token, monkeypatch):
    _armar(monkeypatch, set())
    cabecalho = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/v1/clientes", headers=cabecalho).status_code == 403
    assert client.get("/v1/projetos", headers=cabecalho).status_code == 403
    assert (
        client.get("/v1/financeiro/caixa/atual", headers=cabecalho).status_code == 403
    )


def test_caixa_do_essencial_nao_libera_o_resto_do_financeiro(
    client, admin_token, monkeypatch
):
    """Plano Essencial: rotas de caixa liberadas, contas a pagar bloqueadas."""
    _armar(
        monkeypatch,
        {"cadastros", "movimento", "estoque", "agendamento", "caixa", "configuracoes"},
    )
    cabecalho = {"Authorization": f"Bearer {admin_token}"}
    assert (
        client.get("/v1/financeiro/caixa/atual", headers=cabecalho).status_code != 403
    )
    assert (
        client.get("/v1/financeiro/contas-receber", headers=cabecalho).status_code
        != 403
    )
    assert (
        client.get("/v1/financeiro/contas-pagar", headers=cabecalho).status_code == 403
    )
    assert (
        client.get("/v1/financeiro/plano-contas", headers=cabecalho).status_code == 403
    )


def test_rotas_de_todos_os_planos_ficam_fora_do_gating(
    client, admin_token, monkeypatch
):
    _armar(monkeypatch, set())
    # O gating roda antes das dependências: sem token algum módulo bloqueado daria
    # 403 MODULO_BLOQUEADO; dashboard não está no mapa, então segue para as
    # dependências normais (aqui, 401 de autenticação — não 403 de módulo).
    sem_token = client.get("/v1/dashboard/resumo")
    assert sem_token.status_code != 403
    assert client.get("/health").status_code == 200


def test_flag_desligada_padrao_nao_bloqueia_nada(client, admin_token, monkeypatch):
    """Piloto real: enquanto o RedGest não emite `modulos`, nada muda."""
    monkeypatch.setattr(settings, "gating_modulos", False)
    monkeypatch.setattr(licensa_service, "MODULOS_HABILITADOS", set())
    assert gating.rota_bloqueada("/v1/projetos", set()) is None
    cabecalho = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/v1/projetos", headers=cabecalho).status_code != 403
