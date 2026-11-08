"""Módulo Fiscal (PRD §1.3 / telas_e_fluxos §1.6) — consulta de documentos e resumo.

A emissão depende de gateway externo (inexistente no produto), por isso a API é
somente leitura; os documentos são semeados direto no banco para o teste.
"""

import uuid
from decimal import Decimal

from app.db import SessionLocal
from app.models.enums import ModeloFiscal, NivelAcesso, StatusFiscal
from app.models.fiscal import DocumentoFiscal
from tests.conftest import auth

FILIAL = 1

_MODELOS = [ModeloFiscal.NFE.value, ModeloFiscal.NFCE.value]


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _token_de(client, admin_token, nivel: str) -> str:
    login, senha = f"fis{_u()}", "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={
            "nome": f"Usuário {nivel}",
            "login": login,
            "senha": senha,
            "nivel_acesso": nivel,
        },
    )
    assert resp.status_code == 200, resp.text
    return client.post("/v1/auth/login", json={"login": login, "senha": senha}).json()[
        "data"
    ]["token"]


def _seed_documento(
    *,
    modelo: str = ModeloFiscal.NFE.value,
    status: str = StatusFiscal.AUTORIZADO.value,
    contingencia: bool = False,
    chave: str | None = None,
) -> int:
    db = SessionLocal()
    try:
        doc = DocumentoFiscal(
            filial_id=FILIAL,
            modelo=modelo,
            numero=int(_u(), 16) % 100000,
            serie=1,
            chave_acesso=(chave or _u() * 6)[:44],
            status=status,
            valor_nota=Decimal("312.50"),
            contingencia=contingencia,
            tentativas=0,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc.id
    finally:
        db.close()


def test_lista_documentos_e_filtros(client, admin_token):
    headers = auth(client, admin_token)
    chave = (_u() * 6)[:44]
    autorizado = _seed_documento(status=StatusFiscal.AUTORIZADO.value, chave=chave)
    _seed_documento(modelo=ModeloFiscal.NFCE.value, status=StatusFiscal.REJEITADO.value)

    lista = client.get("/v1/fiscal/documentos", headers=headers)
    assert lista.status_code == 200, lista.text
    ids = [i["id"] for i in lista.json()["data"]]
    assert autorizado in ids

    # Filtro por modelo.
    so_nfe = client.get(
        "/v1/fiscal/documentos", headers=headers, params={"modelo": "nfe"}
    ).json()["data"]
    assert all(i["modelo"] == "nfe" for i in so_nfe)

    # Filtro por status.
    rejeitados = client.get(
        "/v1/fiscal/documentos", headers=headers, params={"status_fiscal": "rejeitado"}
    ).json()["data"]
    assert all(i["status"] == "rejeitado" for i in rejeitados)

    # Busca pela chave de acesso.
    por_chave = client.get(
        "/v1/fiscal/documentos", headers=headers, params={"q": chave[:12]}
    ).json()["data"]
    assert any(i["id"] == autorizado for i in por_chave)


def test_documento_detalhe_e_404(client, admin_token):
    headers = auth(client, admin_token)
    doc_id = _seed_documento()
    detalhe = client.get(f"/v1/fiscal/documentos/{doc_id}", headers=headers)
    assert detalhe.status_code == 200, detalhe.text
    assert detalhe.json()["data"]["id"] == doc_id

    faltante = client.get("/v1/fiscal/documentos/999999999", headers=headers)
    assert faltante.status_code == 404


def test_resumo_e_contingencia(client, admin_token):
    headers = auth(client, admin_token)
    _seed_documento(status=StatusFiscal.AUTORIZADO.value)
    _seed_documento(
        modelo=ModeloFiscal.NFCE.value,
        status=StatusFiscal.REJEITADO.value,
        contingencia=True,
    )

    resumo = client.get("/v1/fiscal/resumo", headers=headers).json()["data"]
    assert resumo["total"] >= 2
    assert resumo["por_modelo"].get("nfce", 0) >= 1
    assert resumo["pendentes"] >= 1
    assert resumo["em_contingencia"] >= 1
    # Sem gateway integrado, a emissão fica indisponível e a tela avisa.
    assert resumo["gateway_configurado"] is False
    assert resumo["gateway_disponivel"] is False
    assert "gateway fiscal" in resumo["mensagem"].lower()


def test_fiscal_visivel_para_caixa_mas_nao_para_operador(client, admin_token):
    caixa = auth(client, _token_de(client, admin_token, NivelAcesso.CAIXA.value))
    assert client.get("/v1/fiscal/documentos", headers=caixa).status_code == 200

    operador = auth(client, _token_de(client, admin_token, NivelAcesso.OPERADOR.value))
    assert client.get("/v1/fiscal/documentos", headers=operador).status_code == 403
    assert client.get("/v1/fiscal/resumo", headers=operador).status_code == 403
