"""Ordem de Serviço / Orçamento (PRD v2.0 §2.1 / telas_e_fluxos §2.1) — servir + transições."""

import uuid
from decimal import Decimal

from tests.conftest import arte_aprovada, auth  # helpers/headers + fixtures do conftest


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_cliente(client, token, nome=None):
    nome = nome or f"Cliente OS {_u()}"
    resp = client.post("/v1/clientes", headers=auth(client, token),
                       json={"nome_razao": nome, "tipo_pessoa": "pf"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _min_payload(cliente, **extra):
    payload = {
        "tipo": "os",
        "cliente_id": cliente["id"],
        "itens": [
            {
                "produto_id": None,
                "descricao_avulsa": "Corte e vinco A4",
                "quantidade": 100,
                "valor_unitario": 0.5,
                "dimensoes": "21x29,7",
            }
        ],
    }
    payload.update(extra)
    return payload


def test_criar_os_calcula_totais(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    resp = client.post(
        "/v1/os", headers=auth(client, admin_token),
        json={
            "tipo": "os",
            "cliente_id": cliente["id"],
            "desconto": 2.00,
            "itens": [
                {"descricao_avulsa": "Corte", "quantidade": 10, "valor_unitario": 5.00},
                {"descricao_avulsa": "Vinco", "quantidade": 2, "valor_unitario": 3.00},
                {"produto_id": None, "descricao_avulsa": "Acabamento", "quantidade": 1,
                 "valor_unitario": 25.00},
            ],
        },
    )
    assert resp.status_code == 200, resp.text
    os_data = resp.json()["data"]
    assert os_data["tipo"] == "os"
    assert os_data["filial_id"] == 1
    assert os_data["status"] == "aberto"
    assert os_data["numero"] is not None
    # 10*5 + 2*3 + 1*25 = 81,00 - 2,00
    assert Decimal(os_data["valor_itens"]) == Decimal("81.00")
    assert Decimal(os_data["valor_total"]) == Decimal("79.00")
    assert len(os_data["itens"]) == 3
    assert os_data["itens"][0]["seq"] == 1
    assert os_data["cliente_nome"] == cliente["nome_razao"]
    assert os_data["criado_por"] is not None


def test_criar_os_sem_itens_422(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    resp = client.post("/v1/os", headers=auth(client, admin_token),
                       json={"tipo": "os", "cliente_id": cliente["id"], "itens": []})
    assert resp.status_code == 422


def test_criar_os_item_sem_referencia_422(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    resp = client.post(
        "/v1/os", headers=auth(client, admin_token),
        json={"tipo": "os", "cliente_id": cliente["id"],
              "itens": [{"quantidade": 1}]},
    )
    assert resp.status_code == 422
    assert "produto_id" in resp.json()["detail"][0]["msg"]


def test_criar_os_desconto_maior_valor_400(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    resp = client.post("/v1/os", headers=auth(client, admin_token),
                       json=_min_payload(cliente, desconto=99.00))
    assert resp.status_code == 400
    assert "desconto" in resp.json()["detail"].lower()


def test_criar_os_cliente_inexistente_409(client, admin_token):
    resp = client.post("/v1/os", headers=auth(client, admin_token),
                       json={"tipo": "os", "cliente_id": 999999999,
                             "itens": [{"descricao_avulsa": "Teste", "quantidade": 1}]})
    assert resp.status_code == 409


def test_numero_os_incrementa(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    first = client.post("/v1/os", headers=auth(client, admin_token),
                        json=_min_payload(cliente)).json()["data"]
    second = client.post("/v1/os", headers=auth(client, admin_token),
                         json=_min_payload(cliente)).json()["data"]
    assert second["numero"] > first["numero"]


def test_orcamento_converte_em_os(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    orc = client.post("/v1/os", headers=auth(client, admin_token),
                      json={"tipo": "orcamento", "cliente_id": cliente["id"],
                            "itens": [{"descricao_avulsa": "Cartão de visita",
                                       "quantidade": 50, "valor_unitario": 1.00}]})
    assert orc.status_code == 200, orc.text
    orc_id = orc.json()["data"]["id"]

    nova = client.post(f"/v1/os/{orc_id}/converter", headers=auth(client, admin_token))
    assert nova.status_code == 200, nova.text
    os_data = nova.json()["data"]
    assert os_data["tipo"] == "os"
    assert os_data["status"] == "aberto"
    assert os_data["orcamento_origem_id"] == orc_id
    assert os_data["numero"] > 0
    assert [i["descricao_avulsa"] for i in os_data["itens"]] == ["Cartão de visita"]
    assert Decimal(os_data["valor_total"]) == Decimal("50.00")

    orig = client.get(f"/v1/os/{orc_id}", headers=auth(client, admin_token)).json()["data"]
    assert orig["status"] == "convertido"

    # não converte duas vezes
    resp = client.post(f"/v1/os/{orc_id}/converter", headers=auth(client, admin_token))
    assert resp.status_code == 400
    assert "aberto" in resp.json()["detail"].lower()


def test_converter_os_ja_os_400(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    os_data = client.post("/v1/os", headers=auth(client, admin_token),
                          json=_min_payload(cliente)).json()["data"]
    resp = client.post(f"/v1/os/{os_data['id']}/converter",
                       headers=auth(client, admin_token))
    assert resp.status_code == 400
    assert "ordem" in resp.json()["detail"].lower()


def test_transicoes_status_com_datas(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    os_data = client.post("/v1/os", headers=auth(client, admin_token),
                          json=_min_payload(cliente)).json()["data"]
    os_id = os_data["id"]

    # M3 (§3.5): produção exige arte aprovada — sobe a arte antes.
    arte_aprovada(client, admin_token, os_id)

    resp = client.patch(f"/v1/os/{os_id}/status", headers=auth(client, admin_token),
                        json={"status": "producao"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "producao"

    resp = client.patch(f"/v1/os/{os_id}/status", headers=auth(client, admin_token),
                        json={"status": "pronta"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "pronta"

    resp = client.patch(f"/v1/os/{os_id}/status", headers=auth(client, admin_token),
                        json={"status": "entregue"})
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "entregue"


def test_transicao_invalida_400(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    os_data = client.post("/v1/os", headers=auth(client, admin_token),
                          json=_min_payload(cliente)).json()["data"]
    # depois de entregue não se volta para produção
    resp = client.patch(f"/v1/os/{os_data['id']}/status",
                        headers=auth(client, admin_token),
                        json={"status": "entregue"})
    assert resp.status_code == 200
    resp = client.patch(f"/v1/os/{os_data['id']}/status",
                        headers=auth(client, admin_token),
                        json={"status": "producao"})
    assert resp.status_code == 400


def test_cancelar_os(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    os_data = client.post("/v1/os", headers=auth(client, admin_token),
                          json=_min_payload(cliente)).json()["data"]

    resp = client.delete(f"/v1/os/{os_data['id']}", headers=auth(client, admin_token))
    assert resp.status_code == 204

    # confere o status por GET (DELETE é no content)
    resp = client.get(f"/v1/os/{os_data['id']}", headers=auth(client, admin_token))
    assert resp.json()["data"]["status"] == "cancelado"

    # não cancela duas vezes
    resp = client.delete(f"/v1/os/{os_data['id']}", headers=auth(client, admin_token))
    assert resp.status_code == 400


def test_entregue_nao_cancela_400(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    os_data = client.post("/v1/os", headers=auth(client, admin_token),
                          json=_min_payload(cliente)).json()["data"]
    arte_aprovada(client, admin_token, os_data["id"])  # gate de produção (M3)
    for s in ("producao", "pronta", "entregue"):
        resp = client.patch(f"/v1/os/{os_data['id']}/status",
                            headers=auth(client, admin_token),
                            json={"status": s})
        assert resp.status_code == 200, resp.text
    resp = client.delete(f"/v1/os/{os_data['id']}", headers=auth(client, admin_token))
    assert resp.status_code == 400


def test_os_lista_filtro_status(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    a = client.post("/v1/os", headers=auth(client, admin_token),
                    json=_min_payload(cliente)).json()["data"]
    arte_aprovada(client, admin_token, a["id"])  # gate de produção (M3)
    client.patch(f"/v1/os/{a['id']}/status", headers=auth(client, admin_token),
                 json={"status": "producao"})
    b = client.post("/v1/os", headers=auth(client, admin_token),
                    json=_min_payload(cliente)).json()["data"]

    resp = client.get("/v1/os", headers=auth(client, admin_token),
                      params={"status": "producao"})
    ids = [os["id"] for os in resp.json()["data"]]
    assert a["id"] in ids and b["id"] not in ids

    resp = client.get("/v1/os", headers=auth(client, admin_token),
                      params={"tipo": "os"})
    assert all(os["tipo"] == "os" for os in resp.json()["data"])


def test_os_busca_por_cliente(client, admin_token):
    cliente = _criar_cliente(client, admin_token)
    client.post("/v1/os", headers=auth(client, admin_token),
                json=_min_payload(cliente))
    nome_busca = cliente["nome_razao"].split("OS ")[1]
    resp = client.get("/v1/os", headers=auth(client, admin_token),
                      params={"q": nome_busca})
    assert resp.status_code == 200
    assert any(os["cliente_nome"] == cliente["nome_razao"] for os in resp.json()["data"])


def test_os_detalhe_404_outra_filial(client, admin_token):
    resp = client.get("/v1/os/999999999", headers=auth(client, admin_token))
    assert resp.status_code == 404


def test_os_operador_pode_criar(client, admin_token):
    import uuid as _u

    login = f"oper_os_{_u.uuid4().hex[:6]}"
    client.post("/v1/usuarios", headers=auth(client, admin_token),
                json={"nome": "Operador OS", "login": login, "senha": "os123456",
                      "nivel_acesso": "operador"})
    resp = client.post("/v1/auth/login", json={"login": login, "senha": "os123456"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["token"]

    cliente = _criar_cliente(client, token)
    resp = client.post("/v1/os", headers=auth(client, token),
                       json=_min_payload(cliente))
    assert resp.status_code == 200, resp.text


def test_os_caixa_bloqueado(client, admin_token):
    login = f"caixa_{_u()}"
    client.post("/v1/usuarios", headers=auth(client, admin_token),
                json={"nome": "Caixa Bloqueado", "login": login, "senha": "cx123456",
                      "nivel_acesso": "caixa"})
    resp = client.post("/v1/auth/login", json={"login": login, "senha": "cx123456"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["token"]

    resp = client.get("/v1/os", headers=auth(client, token))
    assert resp.status_code == 403