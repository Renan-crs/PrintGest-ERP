"""Módulo Projetos — Quadro Kanban (PRD Módulo Projetos §9, PV1–PV5, RN1/RN2/RN6).

Cobre a Fase 1 (Núcleo) do backend, exposta sob o namespace **novo**
`/v1/projetos` (aditivo — `/v1/os` e o quadro antigo seguem intactos):

- estrutura: seeds das listas, CRUD de listas (só gestores; exclusão só admin);
- cartões: criar/editar/arquivar/restaurar, busca;
- movimentação **atômica** com ordenação fracionária e rebalanceamento;
- controle otimista de versão (409);
- visibilidade PV1–PV5 (equipe × membros, contagens, 404 para invisível);
- RBAC (Caixa sem acesso ao módulo).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.db import SessionLocal
from app.models.projetos import Cartao
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
    token = client.post("/v1/auth/login", json={"login": login, "senha": senha}).json()[
        "data"
    ]["token"]
    return token, usuario_id


def _quadro(client, headers) -> dict:
    resp = client.get("/v1/projetos/quadro", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _lista_id(quadro: dict, nome: str) -> int:
    for lista in quadro["listas"]:
        if lista["nome"] == nome:
            return lista["id"]
    raise AssertionError(f"Lista {nome!r} não encontrada no quadro.")


def _criar_lista(client, headers, nome: str, **extra) -> dict:
    resp = client.post(
        "/v1/projetos/quadro/listas", headers=headers, json={"nome": nome, **extra}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _criar_cartao(client, headers, lista_id: int, titulo: str | None = None) -> dict:
    resp = client.post(
        "/v1/projetos/cartoes",
        headers=headers,
        json={"lista_id": lista_id, "titulo": titulo or f"Cartão {_u()}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _mover(client, headers, cartao: dict, lista_id: int, posicao: int):
    return client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/mover",
        headers=headers,
        json={"versao": cartao["versao"], "lista_id": lista_id, "posicao": posicao},
    )


def _definir_posicao(cartao_id: int, valor: str) -> None:
    """Ajusta a posição fracionária direto no banco (para forçar o esgotamento)."""
    db = SessionLocal()
    try:
        cartao = db.get(Cartao, cartao_id)
        cartao.posicao = Decimal(valor)
        db.commit()
    finally:
        db.close()


# ------------------------------------------------------------------ estrutura


def test_quadro_semeia_listas_iniciais(client, admin_token):
    quadro = _quadro(client, auth(client, admin_token))
    assert quadro["filial_id"] == 1
    assert [l["nome"] for l in quadro["listas"]] == [
        "Orçamento",
        "Aguardando",
        "Em produção",
        "Pronta",
        "Entregue",
    ]
    por_nome = {l["nome"]: l for l in quadro["listas"]}
    assert por_nome["Orçamento"]["tipo"] == "orcamento"
    assert por_nome["Aguardando"]["status_os"] == "aprovado"
    assert por_nome["Em produção"]["status_os"] == "producao"
    assert por_nome["Pronta"]["status_os"] == "pronta"
    assert por_nome["Entregue"]["status_os"] == "entregue"
    assert all(isinstance(l["contagem"], int) for l in quadro["listas"])


def test_criar_lista_retorna_dono_e_contagem(client, admin_token):
    header = auth(client, admin_token)
    _, dono_id = _criar_usuario(client, admin_token, "operador")
    nome = f"Pessoal {_u()}"
    lista = _criar_lista(client, header, nome, tipo="usuario", usuario_dono_id=dono_id)
    assert lista["tipo"] == "usuario"
    assert lista["usuario_dono_id"] == dono_id
    assert lista["usuario_dono_nome"]
    assert lista["contagem"] == 0


def test_excluir_lista_com_cartoes_bloqueia(client, admin_token):
    header = auth(client, admin_token)
    lista = _criar_lista(client, header, f"Cheia {_u()}")["id"]
    _criar_cartao(client, header, lista)
    resp = client.delete(f"/v1/projetos/quadro/listas/{lista}", headers=header)
    assert resp.status_code == 400


# --------------------------------------------------------------------- cartões


def test_criar_e_consultar_cartao(client, admin_token):
    header = auth(client, admin_token)
    lista_id = _lista_id(_quadro(client, header), "Em produção")
    titulo = f"Cartão {_u()}"
    resp = client.post(
        "/v1/projetos/cartoes",
        headers=header,
        json={"lista_id": lista_id, "titulo": titulo, "descricao": "detalhe"},
    )
    assert resp.status_code == 201, resp.text
    cartao = resp.json()["data"]
    assert cartao["titulo"] == titulo
    assert cartao["lista_id"] == lista_id
    assert cartao["versao"] == 1
    assert cartao["arquivado"] is False
    assert cartao["membros"] == []
    assert cartao["concluido"] is False

    detalhe = client.get(f"/v1/projetos/cartoes/{cartao['id']}", headers=header)
    assert detalhe.status_code == 200
    assert detalhe.json()["data"]["id"] == cartao["id"]

    busca = client.get(
        "/v1/projetos/cartoes",
        headers=header,
        params={"lista_id": lista_id, "q": titulo},
    )
    assert busca.status_code == 200
    assert cartao["id"] in [c["id"] for c in busca.json()["data"]]
    assert busca.json()["meta"]["total"] >= 1


def test_titulo_obrigatorio(client, admin_token):
    header = auth(client, admin_token)
    lista_id = _lista_id(_quadro(client, header), "Em produção")
    resp = client.post(
        "/v1/projetos/cartoes",
        headers=header,
        json={"lista_id": lista_id, "titulo": "   "},
    )
    assert resp.status_code == 422


def test_atualizar_cartao_incrementa_versao(client, admin_token):
    header = auth(client, admin_token)
    lista_id = _criar_lista(client, header, f"Edição {_u()}")["id"]
    cartao = _criar_cartao(client, header, lista_id)
    resp = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}",
        headers=header,
        json={"versao": cartao["versao"], "titulo": "Novo título"},
    )
    assert resp.status_code == 200, resp.text
    atualizado = resp.json()["data"]
    assert atualizado["titulo"] == "Novo título"
    assert atualizado["versao"] == cartao["versao"] + 1

    # versão obsoleta => 409
    conflito = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}",
        headers=header,
        json={"versao": cartao["versao"], "titulo": "Ainda outro"},
    )
    # versão obsoleta => 409
    conflito = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}",
        headers=header,
        json={"versao": cartao["versao"], "titulo": "Ainda outro"},
    )
    assert conflito.status_code == 409


def test_atualizar_cartao_limpa_campos_com_null(client, admin_token):
    """`null` explícito limpa o campo; campo omitido não é tocado (PATCH parcial)."""
    header = auth(client, admin_token)
    lista_id = _criar_lista(client, header, f"Limpeza {_u()}")["id"]
    criado = client.post(
        "/v1/projetos/cartoes",
        headers=header,
        json={
            "lista_id": lista_id,
            "titulo": f"Com prazo {_u()}",
            "descricao": "algo a apagar",
            "data_entrega": "2999-12-31",
            "lembrete_min": 60,
        },
    ).json()["data"]

    resp = client.patch(
        f"/v1/projetos/cartoes/{criado['id']}",
        headers=header,
        json={
            "versao": criado["versao"],
            "descricao": None,
            "data_entrega": None,
            "lembrete_min": None,
        },
    )
    assert resp.status_code == 200, resp.text
    atualizado = resp.json()["data"]
    assert atualizado["descricao"] is None
    assert atualizado["data_entrega"] is None
    assert atualizado["lembrete_min"] is None
    # Omitir o título não o apaga nem o altera.
    assert atualizado["titulo"] == criado["titulo"]
    assert atualizado["versao"] == criado["versao"] + 1


def test_arquivar_e_restaurar_cartao(client, admin_token):
    header = auth(client, admin_token)
    lista_id = _criar_lista(client, header, f"Arquivo {_u()}")["id"]
    cartao = _criar_cartao(client, header, lista_id)

    arquivado = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/arquivar",
        headers=header,
        json={"versao": cartao["versao"]},
    )
    assert arquivado.status_code == 200, arquivado.text
    assert arquivado.json()["data"]["arquivado"] is True
    versao = arquivado.json()["data"]["versao"]

    ativos = client.get(
        "/v1/projetos/cartoes", headers=header, params={"lista_id": lista_id}
    ).json()["data"]
    assert all(c["id"] != cartao["id"] for c in ativos)

    arquivados = client.get(
        "/v1/projetos/cartoes",
        headers=header,
        params={"lista_id": lista_id, "arquivado": "true"},
    ).json()["data"]
    assert any(c["id"] == cartao["id"] for c in arquivados)

    restaurado = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/restaurar",
        headers=header,
        json={"versao": versao},
    )
    assert restaurado.status_code == 200
    assert restaurado.json()["data"]["arquivado"] is False


# ------------------------------------------------------- movimentação atômica


def test_mover_cartao_entre_listas(client, admin_token):
    header = auth(client, admin_token)
    origem = _criar_lista(client, header, f"Origem {_u()}")["id"]
    destino = _criar_lista(client, header, f"Destino {_u()}")["id"]
    cartao = _criar_cartao(client, header, origem)

    resp = _mover(client, header, cartao, destino, 0)
    assert resp.status_code == 200, resp.text
    movido = resp.json()["data"]
    assert movido["lista_id"] == destino
    assert movido["versao"] == cartao["versao"] + 1


def test_mover_com_versao_obsoleta_retorna_409_e_nao_move(client, admin_token):
    header = auth(client, admin_token)
    lista_a = _criar_lista(client, header, f"A {_u()}")["id"]
    lista_b = _criar_lista(client, header, f"B {_u()}")["id"]
    cartao = _criar_cartao(client, header, lista_a)
    versao_inicial = cartao["versao"]

    assert _mover(client, header, cartao, lista_b, 0).status_code == 200

    # Repetir com a versão antiga falha e **não** move de volta (atomicidade).
    conflito = _mover(client, header, cartao, lista_a, 0)
    assert conflito.status_code == 409
    atual = client.get(f"/v1/projetos/cartoes/{cartao['id']}", headers=header).json()[
        "data"
    ]
    assert atual["lista_id"] == lista_b
    assert atual["versao"] == versao_inicial + 1


def test_reordenar_cartao_dentro_da_lista(client, admin_token):
    header = auth(client, admin_token)
    lista = _criar_lista(client, header, f"Fila {_u()}")["id"]
    primeiro = _criar_cartao(client, header, lista)
    segundo = _criar_cartao(client, header, lista)

    # O segundo vai para o topo.
    resp = _mover(client, header, segundo, lista, 0)
    assert resp.status_code == 200, resp.text

    itens = client.get(
        "/v1/projetos/cartoes", headers=header, params={"lista_id": lista}
    ).json()["data"]
    ids = [c["id"] for c in itens]
    assert ids.index(segundo["id"]) < ids.index(primeiro["id"])


def test_rebalanceamento_quando_espaco_fracionario_esgota(client, admin_token):
    header = auth(client, admin_token)
    lista = _criar_lista(client, header, f"Apertada {_u()}")["id"]
    fora = _criar_lista(client, header, f"Fora {_u()}")["id"]

    c1 = _criar_cartao(client, header, lista)
    c2 = _criar_cartao(client, header, lista)
    # Duas posições vizinhas no limite da precisão (12 casas) não deixam meio.
    _definir_posicao(c1["id"], "1.000000000000")
    _definir_posicao(c2["id"], "1.000000000001")

    intruso = _criar_cartao(client, header, fora)
    resp = _mover(client, header, intruso, lista, 1)
    assert resp.status_code == 200, resp.text

    itens = client.get(
        "/v1/projetos/cartoes", headers=header, params={"lista_id": lista}
    ).json()["data"]
    assert [c["id"] for c in itens] == [c1["id"], intruso["id"], c2["id"]]
    # Após o rebalanceamento, as posições voltam a ter passo uniforme.
    pos = {c["id"]: Decimal(c["posicao"]) for c in itens}
    assert pos[c1["id"]] < pos[intruso["id"]] < pos[c2["id"]]


# ------------------------------------------------------------------ visibilidade


def test_pv2_cartao_restrito_da_404_para_nao_membro(client, admin_token):
    header_admin = auth(client, admin_token)
    token_a, _ = _criar_usuario(client, admin_token, "operador")
    token_b, id_b = _criar_usuario(client, admin_token, "operador")
    token_c, _ = _criar_usuario(client, admin_token, "operador")
    token_ger, _ = _criar_usuario(client, admin_token, "gerente")

    lista = _criar_lista(client, header_admin, f"PV2 {_u()}")["id"]
    cartao = _criar_cartao(client, auth(client, token_a), lista)

    # Sem membros: cartão da equipe, visível até para C (PV1).
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=auth(client, token_c)
        ).status_code
        == 200
    )

    atribuido = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/atribuir",
        headers=auth(client, token_a),
        json={"versao": cartao["versao"], "usuario_id": id_b},
    )
    assert atribuido.status_code == 200, atribuido.text

    # B (membro) vê; gestores veem; C (não membro) recebe 404.
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=auth(client, token_b)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=header_admin
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=auth(client, token_ger)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=auth(client, token_c)
        ).status_code
        == 404
    )
    # E some da busca de C.
    itens = client.get(
        "/v1/projetos/cartoes",
        headers=auth(client, token_c),
        params={"q": cartao["titulo"]},
    ).json()["data"]
    assert all(c["id"] != cartao["id"] for c in itens)


def test_pv3_lista_pessoal_adiciona_e_remove_dono(client, admin_token):
    header_admin = auth(client, admin_token)
    token_b, id_b = _criar_usuario(client, admin_token, "operador")
    equipe = _criar_lista(client, header_admin, f"Equipe {_u()}")["id"]
    pessoal = _criar_lista(
        client, header_admin, f"Pessoal {_u()}", tipo="usuario", usuario_dono_id=id_b
    )["id"]
    cartao = _criar_cartao(client, header_admin, equipe)

    movido = _mover(client, header_admin, cartao, pessoal, 0)
    assert movido.status_code == 200, movido.text
    membros = {m["usuario_id"]: m["origem"] for m in movido.json()["data"]["membros"]}
    assert membros.get(id_b) == "lista"
    # B passa a ver o cartão restrito.
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=auth(client, token_b)
        ).status_code
        == 200
    )

    # Ao sair da lista pessoal, a marcação de origem `lista` é removida.
    versao = movido.json()["data"]["versao"]
    saida = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/mover",
        headers=header_admin,
        json={"versao": versao, "lista_id": equipe, "posicao": 0},
    )
    assert saida.status_code == 200
    assert id_b not in [m["usuario_id"] for m in saida.json()["data"]["membros"]]


def test_pv4_atribuidor_nao_gestor_mantem_acesso(client, admin_token):
    header_admin = auth(client, admin_token)
    token_a, id_a = _criar_usuario(client, admin_token, "operador")
    _, id_b = _criar_usuario(client, admin_token, "operador")
    lista = _criar_lista(client, header_admin, f"PV4 {_u()}")["id"]
    cartao = _criar_cartao(client, auth(client, token_a), lista)

    resp = client.patch(
        f"/v1/projetos/cartoes/{cartao['id']}/atribuir",
        headers=auth(client, token_a),
        json={"versao": cartao["versao"], "usuario_id": id_b},
    )
    assert resp.status_code == 200, resp.text
    membros = {m["usuario_id"]: m["origem"] for m in resp.json()["data"]["membros"]}
    assert membros[id_b] == "manual"
    assert membros[id_a] == "atribuidor"
    assert resp.json()["data"]["ultimo_responsavel_id"] == id_b


def test_pv5_contagem_respeita_visibilidade(client, admin_token):
    header_admin = auth(client, admin_token)
    token_b, id_b = _criar_usuario(client, admin_token, "operador")
    token_c, _ = _criar_usuario(client, admin_token, "operador")
    equipe = _criar_lista(client, header_admin, f"Eq {_u()}")["id"]
    pessoal = _criar_lista(
        client, header_admin, f"P {_u()}", tipo="usuario", usuario_dono_id=id_b
    )["id"]
    cartao = _criar_cartao(client, header_admin, equipe)
    assert _mover(client, header_admin, cartao, pessoal, 0).status_code == 200

    def contagem(token: str) -> int:
        quadro = _quadro(client, auth(client, token))
        return next(l["contagem"] for l in quadro["listas"] if l["id"] == pessoal)

    assert contagem(token_b) == 1
    assert contagem(token_c) == 0
    assert contagem(admin_token) == 1


def test_membros_manuais_add_e_remove(client, admin_token):
    header = auth(client, admin_token)
    token_b, id_b = _criar_usuario(client, admin_token, "operador")
    lista = _criar_lista(client, header, f"Membros {_u()}")["id"]
    cartao = _criar_cartao(client, header, lista)

    add = client.post(
        f"/v1/projetos/cartoes/{cartao['id']}/membros",
        headers=header,
        json={"usuario_id": id_b},
    )
    assert add.status_code == 200, add.text
    assert id_b in [m["usuario_id"] for m in add.json()["data"]["membros"]]
    assert (
        client.get(
            f"/v1/projetos/cartoes/{cartao['id']}", headers=auth(client, token_b)
        ).status_code
        == 200
    )

    rem = client.delete(
        f"/v1/projetos/cartoes/{cartao['id']}/membros/{id_b}", headers=header
    )
    assert rem.status_code == 200
    assert id_b not in [m["usuario_id"] for m in rem.json()["data"]["membros"]]


# -------------------------------------------------------------------------- RBAC


def test_rbac_caixa_sem_acesso_ao_quadro(client, admin_token):
    token_caixa, _ = _criar_usuario(client, admin_token, "caixa")
    resp = client.get("/v1/projetos/quadro", headers=auth(client, token_caixa))
    assert resp.status_code == 403


def test_rbac_estrutura_so_gestores_e_exclusao_so_admin(client, admin_token):
    token_op, _ = _criar_usuario(client, admin_token, "operador")
    token_ger, _ = _criar_usuario(client, admin_token, "gerente")

    # Operador não cria lista.
    negado = client.post(
        "/v1/projetos/quadro/listas",
        headers=auth(client, token_op),
        json={"nome": f"X {_u()}"},
    )
    assert negado.status_code == 403

    # Gerente cria.
    criada = client.post(
        "/v1/projetos/quadro/listas",
        headers=auth(client, token_ger),
        json={"nome": f"Gerente {_u()}"},
    )
    assert criada.status_code == 201, criada.text
    lista_id = criada.json()["data"]["id"]

    # Exclusão definitiva é só do Admin.
    assert (
        client.delete(
            f"/v1/projetos/quadro/listas/{lista_id}", headers=auth(client, token_ger)
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/v1/projetos/quadro/listas/{lista_id}", headers=auth(client, admin_token)
        ).status_code
        == 204
    )


# ------------------------------------------------------------------ não-regressão


def test_v1_os_segue_intacto(client, admin_token):
    """Aditivo: o quadro antigo (`/v1/os`) continua respondendo."""
    resp = client.get("/v1/os", headers=auth(client, admin_token))
    assert resp.status_code == 200
