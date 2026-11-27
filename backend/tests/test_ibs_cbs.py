"""Parametrização IBS/CBS (LC 214/2025) — alíquota vem do contador."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import fiscal_service
from tests.conftest import auth

INICIO = datetime(2027, 1, 1, tzinfo=UTC).isoformat()


def _criar(client, token, **extra):
    corpo = {
        "cnae": "1811301",
        "cbs_pct": "26.5000",
        "ibs_uf_pct": "5.0000",
        "ibs_municipio_pct": "2.0000",
        "vigencia_inicio": INICIO,
        "fonte": "contador",
    }
    corpo.update(extra)
    return client.post(
        "/v1/config/ibs-cbs-aliquotas", headers=auth(client, token), json=corpo
    )


def test_criar_e_listar_aliquota(client, admin_token):
    resp = _criar(client, admin_token)
    assert resp.status_code == 201, resp.text
    dados = resp.json()["data"]
    assert dados["cnae"] == "1811301"
    assert dados["cbs_pct"] == "26.5000"
    assert dados["fonte"] == "contador"

    lista = client.get(
        "/v1/config/ibs-cbs-aliquotas", headers=auth(client, admin_token)
    )
    assert lista.status_code == 200
    assert any(a["id"] == dados["id"] for a in lista.json()["data"])


def test_sem_aliquota_informada_e_rejeitado(client, admin_token):
    resp = _criar(
        client,
        admin_token,
        cnae="1811302",
        cbs_pct=None,
        ibs_uf_pct=None,
        ibs_municipio_pct=None,
    )
    assert resp.status_code == 422
    assert "al menos" in resp.json()["detail"].lower() or "alíquota" in resp.json()["detail"].lower()


def test_duplicata_cnae_vigencia_409(client, admin_token):
    assert _criar(client, admin_token, cnae="1811303").status_code == 201
    resp = _criar(client, admin_token, cnae="1811303")
    assert resp.status_code == 409


def test_encerrar_vigencia(client, admin_token):
    criada = _criar(client, admin_token, cnae="1811304").json()["data"]
    resp = client.put(
        f"/v1/config/ibs-cbs-aliquotas/{criada['id']}/encerrar",
        headers=auth(client, admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["vigencia_fim"] is not None


def test_resumo_fiscal_sinaliza_parametrizacao(client, admin_token):
    # Parâmetro vigente HOJE (a alíquota de 2027 ainda não está em vigor).
    _criar(
        client,
        admin_token,
        cnae="1811305",
        vigencia_inicio=datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
    )
    resp = client.get("/v1/fiscal/resumo", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["ibs_cbs_parametrizado"] is True


def test_bloco_so_vai_ao_gateway_com_flag(monkeypatch):
    payload = {"modelo": "nfe"}
    snapshot = {"cbs_pct": "26.5000"}
    monkeypatch.setattr(fiscal_service.settings, "fiscal_enviar_ibs_cbs", False)
    assert fiscal_service._com_ibs_cbs(dict(payload), snapshot) == payload

    monkeypatch.setattr(fiscal_service.settings, "fiscal_enviar_ibs_cbs", True)
    assert fiscal_service._com_ibs_cbs(dict(payload), snapshot)["ibs_cbs"] == snapshot
