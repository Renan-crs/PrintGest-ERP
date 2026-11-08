"""Módulo Agendamento (PRD §1.3 / telas_e_fluxos §1.3) — Calendário/Lista.

Cobre CRUD, janela de datas (sobreposição), filtros, vínculo com O.S. e RBAC.
Os agendamentos são semeados direto no banco para o teste.
"""

import uuid
from datetime import datetime

from app.db import SessionLocal
from app.models.enums import NivelAcesso, StatusAgenda, TipoAgenda
from app.models.movimento import Agendamento
from tests.conftest import auth

FILIAL = 1


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _token_de(client, admin_token, nivel: str) -> str:
    login, senha = f"age{_u()}", "senha123"
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


def _seed(
    *,
    titulo: str = "Produção",
    tipo: str = TipoAgenda.PRODUCAO.value,
    status: str = StatusAgenda.AGENDADO.value,
    inicio: datetime | None = None,
    fim: datetime | None = None,
    ordem_servico_id: int | None = None,
) -> int:
    db = SessionLocal()
    try:
        ag = Agendamento(
            filial_id=FILIAL,
            tipo=tipo,
            status=status,
            titulo=titulo,
            descricao=None,
            data_hora_inicio=inicio or datetime(2026, 10, 12, 9, 0),
            data_hora_fim=fim,
            ordem_servico_id=ordem_servico_id,
        )
        db.add(ag)
        db.commit()
        db.refresh(ag)
        return ag.id
    finally:
        db.close()


def test_criar_e_detalhe(client, admin_token):
    headers = auth(client, admin_token)
    resp = client.post(
        "/v1/agendamento",
        headers=headers,
        json={
            "titulo": "Entrega material",
            "tipo": "entrega",
            "data_hora_inicio": "2026-10-20T14:00:00",
            "data_hora_fim": "2026-10-20T16:00:00",
        },
    )
    assert resp.status_code == 201, resp.text
    corpo = resp.json()["data"]
    assert corpo["id"] > 0
    assert corpo["tipo"] == "entrega"
    assert corpo["status"] == "agendado"
    assert corpo["ordem_servico_numero"] is None

    detalhe = client.get(f"/v1/agendamento/{corpo['id']}", headers=headers)
    assert detalhe.status_code == 200, detalhe.text
    assert detalhe.json()["data"]["titulo"] == "Entrega material"


def test_criar_valida_titulo_e_ordem(client, admin_token):
    headers = auth(client, admin_token)
    vazio = client.post(
        "/v1/agendamento",
        headers=headers,
        json={"titulo": "   ", "data_hora_inicio": "2026-10-20T14:00:00"},
    )
    assert vazio.status_code == 422, vazio.text

    invertido = client.post(
        "/v1/agendamento",
        headers=headers,
        json={
            "titulo": "X",
            "data_hora_inicio": "2026-10-20T16:00:00",
            "data_hora_fim": "2026-10-20T14:00:00",
        },
    )
    assert invertido.status_code == 422, invertido.text


def test_lista_e_filtros(client, admin_token):
    headers = auth(client, admin_token)
    prod = _seed(titulo="Produção A", tipo=TipoAgenda.PRODUCAO.value)
    entr = _seed(
        titulo="Entrega B",
        tipo=TipoAgenda.ENTREGA.value,
        inicio=datetime(2026, 10, 21, 10, 0),
    )
    concluido = _seed(
        titulo="Concluído C",
        status=StatusAgenda.CONCLUIDO.value,
        inicio=datetime(2026, 10, 22, 8, 0),
    )

    lista = client.get("/v1/agendamento", headers=headers)
    assert lista.status_code == 200, lista.text
    ids = [i["id"] for i in lista.json()["data"]]
    assert {prod, entr, concluido} <= set(ids)

    so_prod = client.get(
        "/v1/agendamento", headers=headers, params={"tipo": "producao"}
    ).json()["data"]
    assert all(i["tipo"] == "producao" for i in so_prod)

    so_concl = client.get(
        "/v1/agendamento", headers=headers, params={"status": "concluido"}
    ).json()["data"]
    assert all(i["status"] == "concluido" for i in so_concl)
    assert concluido in [i["id"] for i in so_concl]


def test_janela_de_datas(client, admin_token):
    headers = auth(client, admin_token)
    # O banco de teste é por sessão: há eventos de outros testes. Por isso a
    # assertividade é por presença/ausência, não por contagem exata.
    alvo = _seed(
        titulo="Janela alvo",
        inicio=datetime(2026, 10, 12, 9, 0),
        fim=datetime(2026, 10, 12, 17, 0),
    )
    fora = _seed(titulo="Janela fora", inicio=datetime(2026, 10, 25, 9, 0))

    # Janela que cobre o dia 12 -> traz o evento alvo (e não o de 25/10).
    janela = client.get(
        "/v1/agendamento",
        headers=headers,
        params={"inicio": "2026-10-12T00:00:00", "fim": "2026-10-12T23:59:59"},
    ).json()["data"]
    ids = [i["id"] for i in janela]
    assert alvo in ids
    assert fora not in ids
    assert next(i for i in janela if i["id"] == alvo)["data_hora_inicio"].startswith(
        "2026-10-12"
    )

    # Janela de 20/10 a 30/10 -> traz o evento de 25/10 (e não o alvo).
    janela2 = client.get(
        "/v1/agendamento",
        headers=headers,
        params={"inicio": "2026-10-20T00:00:00", "fim": "2026-10-30T23:59:59"},
    ).json()["data"]
    ids2 = [i["id"] for i in janela2]
    assert fora in ids2
    assert alvo not in ids2


def test_atualizar_concluir_e_remover(client, admin_token):
    headers = auth(client, admin_token)
    item_id = _seed(titulo="Produção X")

    atualizado = client.put(
        f"/v1/agendamento/{item_id}",
        headers=headers,
        json={
            "titulo": "Produção X (reagendada)",
            "data_hora_inicio": "2026-10-13T10:00:00",
        },
    )
    assert atualizado.status_code == 200, atualizado.text
    assert atualizado.json()["data"]["titulo"] == "Produção X (reagendada)"

    concluido = client.patch(f"/v1/agendamento/{item_id}/concluir", headers=headers)
    assert concluido.status_code == 200, concluido.text
    assert concluido.json()["data"]["status"] == "concluido"

    removido = client.delete(f"/v1/agendamento/{item_id}", headers=headers)
    assert removido.status_code == 204, removido.text
    assert client.get(f"/v1/agendamento/{item_id}", headers=headers).status_code == 404


def test_404_para_agendamento_inexistente(client, admin_token):
    headers = auth(client, admin_token)
    assert client.get("/v1/agendamento/999999999", headers=headers).status_code == 404


def test_rbac_operador_pode_caixa_nao(client, admin_token):
    operador = auth(client, _token_de(client, admin_token, NivelAcesso.OPERADOR.value))
    assert client.get("/v1/agendamento", headers=operador).status_code == 200

    caixa = auth(client, _token_de(client, admin_token, NivelAcesso.CAIXA.value))
    assert client.get("/v1/agendamento", headers=caixa).status_code == 403
