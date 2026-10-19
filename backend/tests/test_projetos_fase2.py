"""Módulo Projetos — Fase 2 (cartão rico): etiquetas, checklists, comentários.

Cobre o incremento **aditivo** da Fase 2 sobre `/v1/projetos` (PRD Módulo
Projetos §9/RF10–RF14), sem tocar a Fase 1 nem `/v1/os`:

- etiquetas: catálogo por filial (só gestores) + aplicar/remover no cartão;
- checklists e itens: progresso no cartão, responsável, ordenação fracionária;
- comentários: resposta em **1** nível, edição pelo autor e soft-delete;
- atividade: log append-only alimentado pelas escritas do cartão;
- isolamento: as sub-rotas herdam a visibilidade (`_buscar_cartao` → 404) e o
  bloqueio de escrita do modo leitura (423).
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.services import licensa_service
from tests.conftest import auth

# ------------------------------------------------------------------- helpers


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _criar_usuario(client, admin_token, nivel: str) -> tuple[str, int]:
    """Cria um usuário do nível pedido e devolve `(token, id)`."""
    login = f"pj{_u()}"
    senha = "senha123"
    resp = client.post(
        "/v1/usuarios",
        headers=auth(client, admin_token),
        json={
            "nome": f"Usuário {nivel} {login}",
            "login": login,
            "senha": senha,
            "nivel_acesso": nivel,
        },
    )
    assert resp.status_code == 200, resp.text
    usuario_id = resp.json()["data"]["id"]
    token = client.post(
        "/v1/auth/login", json={"login": login, "senha": senha}
    ).json()["data"]["token"]
    return token, usuario_id


def _criar_lista(client, headers, nome: str, **extra) -> dict:
    resp = client.post(
        "/v1/projetos/quadro/listas", headers=headers, json={"nome": nome, **extra}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _primeira_lista(client, headers) -> int:
    resp = client.get("/v1/projetos/quadro", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["listas"][0]["id"]


def _criar_cartao(client, headers, lista_id: int, titulo: str | None = None) -> dict:
    resp = client.post(
        "/v1/projetos/cartoes",
        headers=headers,
        json={"lista_id": lista_id, "titulo": titulo or f"Cartão {_u()}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _cartao_novo(client, headers) -> dict:
    return _criar_cartao(client, headers, _lista_nova(client, headers))


def _lista_nova(client, headers) -> int:
    return client.post(
        "/v1/projetos/quadro/listas", headers=headers, json={"nome": f"F2 {_u()}"}
    ).json()["data"]["id"]


def _etiqueta(client, headers, cor: str = "#3498DB") -> dict:
    resp = client.post(
        "/v1/projetos/etiquetas",
        headers=headers,
        json={"nome": f"Etiqueta {_u()}", "cor": cor},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _checklist(client, headers, cartao_id: int, titulo: str = "Passos") -> dict:
    resp = client.post(
        f"/v1/projetos/cartoes/{cartao_id}/checklists",
        headers=headers,
        json={"titulo": titulo},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _item(client, headers, cartao_id: int, checklist_id: int, texto: str, **extra):
    return client.post(
        f"/v1/projetos/cartoes/{cartao_id}/checklists/{checklist_id}/itens",
        headers=headers,
        json={"texto": texto, **extra},
    )


def _comentario(client, headers, cartao_id: int, texto: str, resposta_a_id=None):
    corpo = {"texto": texto}
    if resposta_a_id is not None:
        corpo["resposta_a_id"] = resposta_a_id
    return client.post(
        f"/v1/projetos/cartoes/{cartao_id}/comentarios", headers=headers, json=corpo
    )


# ------------------------------------------------------------------ etiquetas


def test_etiquetas_rbac_operador_le_gestor_administra(client, admin_token):
    token_op, _ = _criar_usuario(client, admin_token, "operador")
    token_ger, _ = _criar_usuario(client, admin_token, "gerente")

    negado = client.post(
        "/v1/projetos/etiquetas",
        headers=auth(client, token_op),
        json={"nome": "Urgente", "cor": "FF0000"},
    )
    assert negado.status_code == 403

    criada = client.post(
        "/v1/projetos/etiquetas",
        headers=auth(client, token_ger),
        json={"nome": "Urgente", "cor": "FF0000"},
    )
    assert criada.status_code == 201, criada.text
    etiqueta = criada.json()["data"]
    assert etiqueta["cor"] == "#FF0000"

    catalogo = client.get("/v1/projetos/etiquetas", headers=auth(client, token_op))
    assert catalogo.status_code == 200
    assert etiqueta["id"] in [e["id"] for e in catalogo.json()["data"]]

    assert (
        client.patch(
            f"/v1/projetos/etiquetas/{etiqueta['id']}",
            headers=auth(client, token_op),
            json={"nome": "Outro"},
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/v1/projetos/etiquetas/{etiqueta['id']}",
            headers=auth(client, token_op),
        ).status_code
        == 403
    )


def test_etiqueta_cor_invalida_e_atualizacao(client, admin_token):
    header = auth(client, admin_token)
    invalida = client.post(
        "/v1/projetos/etiquetas", headers=header, json={"nome": "X", "cor": "ZZZ"}
    )
    assert invalida.status_code == 422

    etiqueta = _etiqueta(client, header, cor="#00FF00")
    resp = client.patch(
        f"/v1/projetos/etiquetas/{etiqueta['id']}",
        headers=header,
        json={"nome": "Revisada", "cor": "#0000FF"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["nome"] == "Revisada"
    assert resp.json()["data"]["cor"] == "#0000FF"


def test_aplicar_e_remover_etiqueta_idempotente(client, admin_token):
    header = auth(client, admin_token)
    etiqueta = _etiqueta(client, header)
    cartao = _cartao_novo(client, header)
    assert cartao["etiquetas"] == []

    aplicada = client.post(
        f"/v1/projetos/cartoes/{cartao['id']}/etiquetas",
        headers=header,
        json={"etiqueta_id": etiqueta["id"]},
    )
    assert aplicada.status_code == 200, aplicada.text
    assert [e["id"] for e in aplicada.json()["data"]["etiquetas"]] == [etiqueta["id"]]

    # Aplicar de novo não duplica nem reclama.
    repetida = client.post(
        f"/v1/projetos/cartoes/{cartao['id']}/etiquetas",
        headers=header,
        json={"etiqueta_id": etiqueta["id"]},
    )
    assert repetida.status_code == 200
    assert len(repetida.json()["data"]["etiquetas"]) == 1

    removida = client.delete(
        f"/v1/projetos/cartoes/{cartao['id']}/etiquetas/{etiqueta['id']}",
        headers=header,
    )
    assert removida.status_code == 200
    assert removida.json()["data"]["etiquetas"] == []


def test_aplicar_etiqueta_inexistente_404(client, admin_token):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)
    resp = client.post(
        f"/v1/projetos/cartoes/{cartao['id']}/etiquetas",
        headers=header,
        json={"etiqueta_id": 999_999_999},
    )
    assert resp.status_code == 404


def test_excluir_etiqueta_remove_vinculo_do_cartao(client, admin_token):
    header = auth(client, admin_token)
    etiqueta = _etiqueta(client, header)
    cartao = _cartao_novo(client, header)
    client.post(
        f"/v1/projetos/cartoes/{cartao['id']}/etiquetas",
        headers=header,
        json={"etiqueta_id": etiqueta["id"]},
    )

    assert (
        client.delete(
            f"/v1/projetos/etiquetas/{etiqueta['id']}", headers=header
        ).status_code
        == 204
    )
    atual = client.get(f"/v1/projetos/cartoes/{cartao['id']}", headers=header)
    assert atual.json()["data"]["etiquetas"] == []


# ------------------------------------------------------------------ checklists


def test_checklist_itens_concluidos_e_progresso(client, admin_token):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)
    assert cartao["checklist_total"] == 0

    checklist = _checklist(client, header, cartao["id"], "Diagramação")
    assert checklist["total"] == 0
    assert checklist["itens"] == []

    primeiro = _item(client, header, cartao["id"], checklist["id"], "Revisar arte")
    assert primeiro.status_code == 201, primeiro.text
    assert primeiro.json()["data"]["concluido"] is False
    segundo = _item(
        client,
        header,
        cartao["id"],
        checklist["id"],
        "Aprovar com o cliente",
        data_entrega="2999-01-01",
    )
    assert segundo.status_code == 201

    concluido = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/checklists/{checklist['id']}"
        f"/itens/{primeiro.json()['data']['id']}",
        headers=header,
        json={"concluido": True},
    )
    assert concluido.status_code == 200, concluido.text
    assert concluido.json()["data"]["concluido"] is True

    atual = client.get(f"/v1/projetos/cartoes/{cartao['id']}", headers=header)
    assert atual.json()["data"]["checklist_total"] == 2
    assert atual.json()["data"]["checklist_concluidos"] == 1

    lista = client.get(
        f"/v1/projetos/cartoes/{cartao['id']}/checklists", headers=header
    ).json()["data"]
    assert len(lista) == 1
    assert lista[0]["total"] == 2 and lista[0]["concluidos"] == 1
    assert [i["texto"] for i in lista[0]["itens"]] == [
        "Revisar arte",
        "Aprovar com o cliente",
    ]


def test_item_responsavel_e_exclusao(client, admin_token):
    header = auth(client, admin_token)
    _, responsavel_id = _criar_usuario(client, admin_token, "operador")
    cartao = _cartao_novo(client, header)
    checklist = _checklist(client, header, cartao["id"])

    criado = _item(
        client,
        header,
        cartao["id"],
        checklist["id"],
        "Imprimir prova",
        responsavel_id=responsavel_id,
    )
    assert criado.status_code == 201, criado.text
    item = criado.json()["data"]
    assert item["responsavel_id"] == responsavel_id
    assert item["responsavel_nome"]

    removido = client.delete(
        f"/v1/projetos/cartoes/{cartao['id']}/checklists/{checklist['id']}"
        f"/itens/{item['id']}",
        headers=header,
    )
    assert removido.status_code == 204
    vazio = client.get(
        f"/v1/projetos/cartoes/{cartao['id']}/checklists", headers=header
    ).json()["data"]
    assert vazio[0]["itens"] == []


def test_reordenar_checklists(client, admin_token):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)
    primeiro = _checklist(client, header, cartao["id"], "Primeiro")
    segundo = _checklist(client, header, cartao["id"], "Segundo")

    resp = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/checklists/{segundo['id']}",
        headers=header,
        json={"posicao": 0},
    )
    assert resp.status_code == 200, resp.text
    lista = client.get(
        f"/v1/projetos/cartoes/{cartao['id']}/checklists", headers=header
    ).json()["data"]
    assert [c["id"] for c in lista] == [segundo["id"], primeiro["id"]]


def test_checklist_de_outro_cartao_404(client, admin_token):
    header = auth(client, admin_token)
    cartao_a = _cartao_novo(client, header)
    cartao_b = _cartao_novo(client, header)
    checklist = _checklist(client, header, cartao_a["id"])

    resp = _item(client, header, cartao_b["id"], checklist["id"], "fora do cartão")
    assert resp.status_code == 404


# ---------------------------------------------------------------- comentários


def test_resposta_em_um_nivel_apenas(client, admin_token):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)

    raiz = _comentario(client, header, cartao["id"], "Alguém viu o arquivo?")
    assert raiz.status_code == 201, raiz.text
    raiz_id = raiz.json()["data"]["id"]

    resposta = _comentario(client, header, cartao["id"], "Eu vi", raiz_id)
    assert resposta.status_code == 201
    assert resposta.json()["data"]["resposta_a_id"] == raiz_id

    # Responder a uma resposta é recusado (1 nível).
    aninhado = _comentario(
        client, header, cartao["id"], "de novo", resposta.json()["data"]["id"]
    )
    assert aninhado.status_code == 400

    itens = client.get(
        f"/v1/projetos/cartoes/{cartao['id']}/comentarios", headers=header
    ).json()["data"]
    assert len(itens) == 2


def test_comentario_so_autor_edita_e_soft_delete(client, admin_token):
    header_admin = auth(client, admin_token)
    token_b, _ = _criar_usuario(client, admin_token, "operador")
    header_b = auth(client, token_b)
    cartao = _criar_cartao(client, header_b, _lista_nova(client, header_admin))

    criado = _comentario(client, header_b, cartao["id"], "rascunho")
    assert criado.status_code == 201, criado.text
    comentario_id = criado.json()["data"]["id"]

    # Quem não é o autor não edita.
    assert (
        client.patch(
            f"/v1/projetos/cartoes/{cartao['id']}/comentarios/{comentario_id}",
            headers=header_admin,
            json={"texto": "invasão"},
        ).status_code
        == 403
    )

    editado = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/comentarios/{comentario_id}",
        headers=header_b,
        json={"texto": "versão final"},
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["data"]["texto"] == "versão final"
    assert editado.json()["data"]["editado_em"]

    excluido = client.delete(
        f"/v1/projetos/cartoes/{cartao['id']}/comentarios/{comentario_id}",
        headers=header_b,
    )
    assert excluido.status_code == 200
    assert excluido.json()["data"]["excluido"] is True
    assert excluido.json()["data"]["texto"] is None

    # Persiste na listagem (histórico), marcado como excluído.
    itens = client.get(
        f"/v1/projetos/cartoes/{cartao['id']}/comentarios", headers=header_b
    ).json()["data"]
    assert any(i["id"] == comentario_id and i["excluido"] for i in itens)


def test_gestor_modera_comentario_de_outro(client, admin_token):
    header_admin = auth(client, admin_token)
    token_b, _ = _criar_usuario(client, admin_token, "operador")
    token_ger, _ = _criar_usuario(client, admin_token, "gerente")
    cartao = _criar_cartao(
        client, auth(client, token_b), _lista_nova(client, header_admin)
    )

    criado = _comentario(client, auth(client, token_b), cartao["id"], "algo")
    assert criado.status_code == 201

    resp = client.delete(
        f"/v1/projetos/cartoes/{cartao['id']}/comentarios"
        f"/{criado.json()['data']['id']}",
        headers=auth(client, token_ger),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["excluido"] is True


def test_cartao_traz_contagem_de_comentarios(client, admin_token):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)
    for texto in ("primeiro", "segundo"):
        assert _comentario(client, header, cartao["id"], texto).status_code == 201

    atual = client.get(f"/v1/projetos/cartoes/{cartao['id']}", headers=header)
    assert atual.json()["data"]["comentarios_total"] == 2


# ------------------------------------------------------------------ atividade


def test_atividade_registra_as_escritas(client, admin_token):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)
    _etiqueta(client, header)  # só para garantir filial com catálogo
    etiqueta = _etiqueta(client, header)
    client.post(
        f"/v1/projetos/cartoes/{cartao['id']}/etiquetas",
        headers=header,
        json={"etiqueta_id": etiqueta["id"]},
    )
    checklist = _checklist(client, header, cartao["id"], "Execução")
    passo = _item(client, header, cartao["id"], checklist["id"], "Passo 1")
    assert passo.status_code == 201
    assert _comentario(client, header, cartao["id"], "combinado").status_code == 201

    destino = _lista_nova(client, header)
    versao = client.get(
        f"/v1/projetos/cartoes/{cartao['id']}", headers=header
    ).json()["data"]["versao"]
    assert (
        client.patch(
            f"/v1/projetos/cartoes/{cartao['id']}/mover",
            headers=header,
            json={"versao": versao, "lista_id": destino, "posicao": 0},
        ).status_code
        == 200
    )

    log = client.get(f"/v1/projetos/cartoes/{cartao['id']}/atividade", headers=header)
    assert log.status_code == 200, log.text
    eventos = log.json()["data"]
    tipos = [e["tipo"] for e in eventos]
    for esperado in (
        "criado",
        "etiqueta_add",
        "checklist_criado",
        "item_criado",
        "comentario",
        "movido",
    ):
        assert esperado in tipos, tipos
    # Mais recente primeiro.
    assert tipos[0] == "movido"
    assert eventos[0]["usuario_nome"]


# ------------------------------------------------------------------ isolamento


def test_subrotas_respeitam_visibilidade_do_cartao(client, admin_token):
    header = auth(client, admin_token)
    token_a, id_a = _criar_usuario(client, admin_token, "operador")
    token_c, _ = _criar_usuario(client, admin_token, "operador")

    cartao = _cartao_novo(client, header)
    atribuido = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/atribuir",
        headers=header,
        json={"versao": cartao["versao"], "usuario_id": id_a},
    )
    assert atribuido.status_code == 200, atribuido.text

    header_c = auth(client, token_c)
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}/checklists", headers=header_c
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}/comentarios", headers=header_c
        ).status_code
        == 404
    )
    assert (
        _comentario(client, header_c, cartao["id"], "não posso").status_code == 404
    )
    # O atribuído continua vendo.
    header_a = auth(client, token_a)
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}/checklists", headers=header_a
        ).status_code
        == 200
    )


def test_rbac_caixa_sem_acesso_a_fase2(client, admin_token):
    token_caixa, _ = _criar_usuario(client, admin_token, "caixa")
    header = auth(client, token_caixa)
    assert client.get("/v1/projetos/etiquetas", headers=header).status_code == 403
    assert (
        _comentario(client, header, 1, "sem acesso").status_code == 403
    )


def test_modo_leitura_bloqueia_escritas_da_fase2(client, admin_token, monkeypatch):
    header = auth(client, admin_token)
    cartao = _cartao_novo(client, header)

    monkeypatch.setattr(settings, "licenca_desabilitada", False)
    anterior = dict(licensa_service.ESTADO)
    licensa_service.ESTADO["modo_leitura"] = True
    try:
        bloqueado = _comentario(client, header, cartao["id"], "não deveria entrar")
        assert bloqueado.status_code == 423
        # GET segue liberado.
        assert (
            client.get(
                f"/v1/projetos/cartoes/{cartao['id']}/comentarios", headers=header
            ).status_code
            == 200
        )
    finally:
        licensa_service.ESTADO.clear()
        licensa_service.ESTADO.update(anterior)
