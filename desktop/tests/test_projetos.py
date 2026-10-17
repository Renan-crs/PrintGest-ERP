"""Testes do módulo Projetos (Quadro Kanban) sobre `/v1/projetos`.

Diferente do quadro antigo (1 projeto = 1 O.S. via `/v1/os`), aqui as colunas
são as **listas** do servidor e cada cartão é uma unidade independente. O quadro
carrega com duas consultas (`/quadro` + `/cartoes`) e o arrastar-e-soltar usa
`PATCH /cartoes/{id}/mover` com um **índice** (0-based) e a `versao` lida.

O `MockTransport` abaixo emula o backend o suficiente para exercitar a tela: o
quadro, os cartões (busca/arquivo), a movimentação, a ficha do cartão (com
membros) e a estrutura de listas.
"""

from __future__ import annotations

import copy
import json

import httpx
import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from printgest.core.api import Api
from printgest.ui.kanban import MIME_CARTAO
from printgest.ui.modulos.projetos import DialogoCartao, DialogoListas, PaginaProjetos


def _lista(ident: int, nome: str) -> dict:
    return {
        "id": ident,
        "quadro_id": 1,
        "nome": nome,
        "posicao": f"{ident}.000000000000",
        "tipo": "livre",
        "status_os": None,
        "usuario_dono_id": None,
        "usuario_dono_nome": None,
        "fornecedor_id": None,
        "arquivada": False,
        "contagem": 0,
    }


def _cartao(ident: int, lista_id: int, titulo: str, **extra) -> dict:
    base = {
        "id": ident,
        "filial_id": 1,
        "lista_id": lista_id,
        "posicao": f"{ident}.000000000000",
        "titulo": titulo,
        "descricao": None,
        "data_inicio": None,
        "data_entrega": None,
        "lembrete_min": None,
        "concluido": False,
        "concluido_em": None,
        "ordem_servico_id": None,
        "ultimo_responsavel_id": None,
        "ultimo_responsavel_nome": None,
        "terceiro_fornecedor_id": None,
        "terceiro_prazo": None,
        "terceiro_custo": None,
        "arquivado": False,
        "versao": 1,
        "membros": [],
        "criado_por": 1,
        "criado_em": "2026-01-01T09:00:00",
        "atualizado_em": "2026-01-01T09:00:00",
    }
    base.update(extra)
    return base


_LISTAS = [_lista(1, "Orçamento"), _lista(2, "Em produção"), _lista(3, "Entregue")]

_CARTOES = [
    _cartao(10, 1, "Banner 2x1", data_entrega="2999-01-01"),
    _cartao(11, 2, "Cartão atrasado", data_entrega="2020-01-01", versao=2),
    _cartao(
        12,
        2,
        "Cartão de outra pessoa",
        ultimo_responsavel_id=7,
        ultimo_responsavel_nome="Vina",
        membros=[{"usuario_id": 7, "nome": "Vina", "origem": "manual"}],
    ),
]

_USUARIOS = [
    {"id": 1, "nome": "Ana", "login": "ana"},
    {"id": 7, "nome": "Vina", "login": "vina"},
]

# Molde imutável; `ESTADO` é a cópia mutável usada pelo handler em cada teste.
ESTADO: dict = {}


@pytest.fixture(autouse=True)
def _dados_limpos():
    ESTADO.update(
        {
            "listas": copy.deepcopy(_LISTAS),
            "cartoes": copy.deepcopy(_CARTOES),
            "usuarios": copy.deepcopy(_USUARIOS),
            "requisicoes": [],
        }
    )
    yield


@pytest.fixture(autouse=True)
def _qt(app):
    """Garante o QApplication (offscreen) antes de montar qualquer widget."""
    return app


def _quadro_json() -> dict:
    listas = ESTADO["listas"]
    contagens: dict[int, int] = {}
    for cartao in ESTADO["cartoes"]:
        if not cartao["arquivado"]:
            contagens[cartao["lista_id"]] = contagens.get(cartao["lista_id"], 0) + 1
    saida = []
    for lista in listas:
        item = dict(lista)
        item["contagem"] = contagens.get(lista["id"], 0)
        saida.append(item)
    return {"id": 1, "filial_id": 1, "nome": "Projetos", "listas": saida}


def _pagina_json(itens: list[dict]) -> dict:
    return {"data": itens, "meta": {"total": len(itens), "limit": 1000, "offset": 0}}


def _handler(request: httpx.Request) -> httpx.Response:
    ESTADO["requisicoes"].append(request)
    metodo = request.method
    caminho = request.url.path

    if caminho == "/v1/usuarios":
        return httpx.Response(200, json=_pagina_json(ESTADO["usuarios"]))

    if caminho == "/v1/projetos/quadro" and metodo == "GET":
        return httpx.Response(200, json={"data": _quadro_json()})

    if caminho == "/v1/projetos/cartoes" and metodo == "GET":
        params = request.url.params
        arquivado = params.get("arquivado") == "true"
        termo = (params.get("q") or "").strip().lower()
        linhas = [c for c in ESTADO["cartoes"] if bool(c["arquivado"]) == arquivado]
        if params.get("lista_id"):
            linhas = [c for c in linhas if c["lista_id"] == int(params["lista_id"])]
        if termo:
            linhas = [
                c
                for c in linhas
                if termo in c["titulo"].lower()
                or termo in (c.get("descricao") or "").lower()
            ]
        return httpx.Response(200, json=_pagina_json(linhas))

    if caminho == "/v1/projetos/cartoes" and metodo == "POST":
        dados = json.loads(request.content)
        novo = _cartao(max((c["id"] for c in ESTADO["cartoes"]), default=0) + 1, dados["lista_id"], dados["titulo"])
        for campo in ("descricao", "data_inicio", "data_entrega", "lembrete_min"):
            novo[campo] = dados.get(campo)
        ESTADO["cartoes"].append(novo)
        return httpx.Response(201, json={"data": novo})

    if caminho.startswith("/v1/projetos/cartoes/"):
        partes = caminho.split("/")
        cartao_id = int(partes[4])
        cartao = next((c for c in ESTADO["cartoes"] if c["id"] == cartao_id), None)
        if cartao is None:
            return httpx.Response(404, json={"detail": "Cartão não encontrado."})
        acao = partes[5] if len(partes) > 5 else None

        if acao is None and metodo == "GET":
            return httpx.Response(200, json={"data": cartao})
        if acao is None and metodo == "PATCH":
            dados = json.loads(request.content)
            if dados.get("versao") != cartao["versao"]:
                return httpx.Response(409, json={"detail": "Versão desatualizada."})
            for campo in (
                "titulo",
                "descricao",
                "data_inicio",
                "data_entrega",
                "lembrete_min",
                "concluido",
            ):
                if campo in dados and dados[campo] is not None:
                    cartao[campo] = dados[campo]
            cartao["versao"] += 1
            return httpx.Response(200, json={"data": cartao})

        if acao == "mover" and metodo == "PATCH":
            dados = json.loads(request.content)
            if dados.get("versao") != cartao["versao"]:
                return httpx.Response(409, json={"detail": "Versão desatualizada."})
            cartao["lista_id"] = dados["lista_id"]
            cartao["posicao"] = f"{cartao['posicao'].split('.')[0]}.{dados['posicao']:06d}"
            cartao["posicao_indice"] = dados["posicao"]
            cartao["versao"] += 1
            return httpx.Response(200, json={"data": cartao})

        if acao in ("arquivar", "restaurar") and metodo == "PATCH":
            dados = json.loads(request.content)
            if dados.get("versao") != cartao["versao"]:
                return httpx.Response(409, json={"detail": "Versão desatualizada."})
            cartao["arquivado"] = acao == "arquivar"
            cartao["versao"] += 1
            return httpx.Response(200, json={"data": cartao})

        if acao == "atribuir" and metodo == "PATCH":
            dados = json.loads(request.content)
            if dados.get("versao") != cartao["versao"]:
                return httpx.Response(409, json={"detail": "Versão desatualizada."})
            uid = dados["usuario_id"]
            nome = next((u["nome"] for u in ESTADO["usuarios"] if u["id"] == uid), "?")
            cartao["ultimo_responsavel_id"] = uid
            cartao["ultimo_responsavel_nome"] = nome
            if not any(m["usuario_id"] == uid for m in cartao["membros"]):
                cartao["membros"].append(
                    {"usuario_id": uid, "nome": nome, "origem": "manual"}
                )
            cartao["versao"] += 1
            return httpx.Response(200, json={"data": cartao})

        if acao == "membros" and metodo == "POST":
            dados = json.loads(request.content)
            uid = dados["usuario_id"]
            nome = next((u["nome"] for u in ESTADO["usuarios"] if u["id"] == uid), "?")
            if not any(m["usuario_id"] == uid for m in cartao["membros"]):
                cartao["membros"].append(
                    {"usuario_id": uid, "nome": nome, "origem": "manual"}
                )
            cartao["versao"] += 1
            return httpx.Response(200, json={"data": cartao})

        if acao == "membros" and metodo == "DELETE":
            membro_id = int(partes[6])
            cartao["membros"] = [
                m for m in cartao["membros"] if m["usuario_id"] != membro_id
            ]
            cartao["versao"] += 1
            return httpx.Response(200, json={"data": cartao})

    if caminho == "/v1/projetos/quadro/listas" and metodo == "POST":
        dados = json.loads(request.content)
        novo_id = max((l["id"] for l in ESTADO["listas"]), default=0) + 1
        ESTADO["listas"].append(_lista(novo_id, dados["nome"]))
        return httpx.Response(201, json={"data": _lista(novo_id, dados["nome"])})

    if caminho.startswith("/v1/projetos/quadro/listas/"):
        partes = caminho.split("/")
        lista_id = int(partes[5])
        lista = next((l for l in ESTADO["listas"] if l["id"] == lista_id), None)
        if lista is None:
            return httpx.Response(404, json={"detail": "Lista não encontrada."})
        if metodo == "PATCH" and (len(partes) == 6):
            dados = json.loads(request.content)
            if dados.get("nome"):
                lista["nome"] = dados["nome"]
            return httpx.Response(200, json={"data": lista})
        if metodo == "PATCH" and partes[6] == "arquivar":
            lista["arquivada"] = True
            return httpx.Response(200, json={"data": lista})
        if metodo == "DELETE":
            ocupados = [
                c
                for c in ESTADO["cartoes"]
                if c["lista_id"] == lista_id and not c["arquivado"]
            ]
            if ocupados:
                return httpx.Response(
                    400, json={"detail": "Mova ou arquive os cartões antes."}
                )
            ESTADO["listas"] = [l for l in ESTADO["listas"] if l["id"] != lista_id]
            return httpx.Response(204)

    return httpx.Response(404, json={"detail": f"rota não esperada: {caminho}"})


def _api() -> Api:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana"}})
    return api


def _pagina(nivel: str = "gerente", modo_leitura: bool = False) -> PaginaProjetos:
    return PaginaProjetos(_api(), modo_leitura=modo_leitura, nivel=nivel)


def _patches(caminho_sufixo: str) -> list[httpx.Request]:
    return [
        r
        for r in ESTADO["requisicoes"]
        if r.method == "PATCH" and r.url.path.endswith(caminho_sufixo)
    ]


def _soltar(coluna, item_id, y: int = 12) -> None:
    dados = QMimeData()
    dados.setData(MIME_CARTAO, str(item_id).encode("utf-8"))
    evento = QDropEvent(
        QPointF(12, y),
        Qt.DropAction.MoveAction,
        dados,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    coluna.dropEvent(evento)


# --------------------------------------------------------------- quadro

def test_quadro_renderiza_listas_e_cartoes():
    pagina = _pagina()
    assert pagina._quadro.coluna("1")._titulo.text() == "ORÇAMENTO"
    assert pagina._quadro.contagem("1") == 1
    assert pagina._quadro.contagem("2") == 2
    assert pagina._quadro.coluna_do(12) == "2"


def test_colunas_vem_do_servidor_na_ordem():
    pagina = _pagina()
    assert [c for c, _r in pagina._quadro._rotulos] == ["1", "2", "3"]


def test_cartao_mostra_responsavel_e_prazo():
    pagina = _pagina()
    cartao = next(
        c for c in pagina._quadro.coluna("2").cartoes() if c.id_registro == 12
    )
    assert "Vina" in cartao.toolTip()


def test_cartao_atrasado_recebe_badge():
    pagina = _pagina()
    cartao = next(
        c for c in pagina._quadro.coluna("2").cartoes() if c.id_registro == 11
    )
    assert "Atrasado" in [b.text() for b in cartao.findChildren(QLabel)]


def test_estado_vazio_sem_listas():
    ESTADO["listas"] = []
    pagina = _pagina()
    assert pagina._listas == []
    assert pagina._quadro.isHidden() is True
    assert pagina._vazio.isHidden() is False


def test_busca_envia_q_e_filtra():
    pagina = _pagina()
    pagina.recarregar("Banner")
    assert pagina._quadro.contagem("1") == 1
    assert pagina._quadro.contagem("2") == 0
    buscas = [r for r in ESTADO["requisicoes"] if r.url.path == "/v1/projetos/cartoes"]
    assert buscas[-1].url.params.get("q") == "Banner"


def test_quadro_sem_rolagem_horizontal(app):
    # 3 colunas de largura mínima cabem na tela; o quadro não rola na horizontal.
    pagina = _pagina()
    container = QWidget()
    caixa = QVBoxLayout(container)
    caixa.setContentsMargins(0, 0, 0, 0)
    caixa.addWidget(pagina)
    container.resize(1216, 720)
    container.show()
    app.processEvents()
    assert pagina._quadro._area.horizontalScrollBar().maximum() == 0
    container.close()


# ------------------------------------------------------------ movimentação

def test_soltar_em_outra_lista_move_com_indice_e_versao():
    pagina = _pagina()
    _soltar(pagina._quadro.coluna("3"), 12)
    patch = _patches("/mover")[-1]
    dados = json.loads(patch.content)
    assert patch.url.path == "/v1/projetos/cartoes/12/mover"
    assert dados["lista_id"] == 3
    assert dados["posicao"] == 0
    assert dados["versao"] == 1
    assert pagina._quadro.coluna_do(12) == "3"


def test_menu_mover_anexa_ao_final():
    pagina = _pagina()
    # Menu de contexto envia indice -1 → posição = quantidade de cartões no destino.
    pagina._quadro.coluna("2").cartoes()[0].mover_solicitado.emit(10, "2", -1)
    dados = json.loads(_patches("/mover")[-1].content)
    assert dados["lista_id"] == 2
    assert dados["posicao"] == 2  # destino já tinha 2 cartões


def test_soltar_na_mesma_posicao_nao_chama_api():
    pagina = _pagina()
    assert pagina._indice_efetivo(11, "2", "2", 0) == 0  # cartão 11 já é o índice 0
    pagina._mover(11, "2", 0)
    assert _patches("/mover") == []


def test_reordenar_dentro_da_lista_ajusta_o_indice():
    pagina = _pagina()
    # Cartão 11 (índice 0) solto abaixo do 12 (índice 1) → servidor recebe índice 1.
    assert pagina._indice_efetivo(11, "2", "2", 2) == 1


def test_drop_event_calcula_indice_pela_metade_do_cartao():
    pagina = _pagina()
    coluna = pagina._quadro.coluna("2")
    for indice, cartao in enumerate(coluna.cartoes()):
        cartao.setGeometry(0, indice * 60, 100, 50)
    assert coluna.indice_para_posicao(QPoint(0, 0)) == 0
    assert coluna.indice_para_posicao(QPoint(0, 10_000)) == 2


# --------------------------------------------------------------- modo leitura

def test_modo_leitura_bloqueia_arraste_e_botoes():
    pagina = _pagina(modo_leitura=True)
    coluna = pagina._quadro.coluna("1")
    assert coluna.acceptDrops() is False
    assert coluna.cartoes()[0].arrastavel is False
    assert pagina._btn_novo.isEnabled() is False


def test_modo_leitura_mover_avisa_e_nao_grava(monkeypatch):
    avisos: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[1]))
    pagina = _pagina(modo_leitura=True)
    pagina._mover(10, "2", 0)
    assert _patches("/mover") == []
    assert "Modo leitura" in avisos


# ----------------------------------------------------------- RBAC de estrutura

def test_botao_de_listas_so_para_gestor():
    assert _pagina(nivel="gerente")._btn_listas.isHidden() is False
    assert _pagina(nivel="operador")._btn_listas.isHidden() is True
    assert _pagina(nivel="admin")._btn_listas.isHidden() is False


def test_novo_cartao_sem_listas_avisa(monkeypatch):
    ESTADO["listas"] = []
    avisos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[2]))
    pagina = _pagina()
    pagina._novo_cartao()
    assert "lista" in avisos[0].lower()

# --------------------------------------------------------------- ficha cartão

def test_dialogo_cria_cartao():
    api = _api()
    dialogo = DialogoCartao(
        api, listas=copy.deepcopy(_LISTAS), usuarios=copy.deepcopy(_USUARIOS), lista_padrao=2
    )
    dialogo._titulo.definir("Novo trabalho")
    dialogo._salvar()
    criado = next(c for c in ESTADO["cartoes"] if c["titulo"] == "Novo trabalho")
    assert criado["lista_id"] == 2
    assert dialogo._cartao["id"] == criado["id"]


def test_dialogo_exige_titulo(monkeypatch):
    avisos: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[1]))
    api = _api()
    dialogo = DialogoCartao(api, listas=copy.deepcopy(_LISTAS), usuarios=[])
    dialogo._titulo.definir("   ")
    dialogo._salvar()
    assert avisos
    assert not any(c["titulo"].strip() == "" for c in ESTADO["cartoes"])


def test_dialogo_edita_e_atribui():
    api = _api()
    cartao = copy.deepcopy(next(c for c in ESTADO["cartoes"] if c["id"] == 10))
    dialogo = DialogoCartao(
        api, cartao=cartao, listas=copy.deepcopy(_LISTAS), usuarios=copy.deepcopy(_USUARIOS)
    )
    dialogo._titulo.definir("Banner revisado")
    dialogo._responsavel.definir(7)
    dialogo._salvar()

    atual = next(c for c in ESTADO["cartoes"] if c["id"] == 10)
    assert atual["titulo"] == "Banner revisado"
    assert atual["ultimo_responsavel_id"] == 7
    assert any(m["usuario_id"] == 7 for m in atual["membros"])
    assert atual["versao"] >= 2


def test_dialogo_arquiva():
    api = _api()
    cartao = copy.deepcopy(next(c for c in ESTADO["cartoes"] if c["id"] == 11))
    dialogo = DialogoCartao(api, cartao=cartao, usuarios=[])
    dialogo._arquivar()
    assert next(c for c in ESTADO["cartoes"] if c["id"] == 11)["arquivado"] is True


def test_dialogo_adiciona_e_remove_membro():
    api = _api()
    cartao = copy.deepcopy(next(c for c in ESTADO["cartoes"] if c["id"] == 12))
    dialogo = DialogoCartao(api, cartao=cartao, usuarios=copy.deepcopy(_USUARIOS))

    dialogo._novo_membro.setCurrentIndex(
        dialogo._novo_membro.findData(1)
    )
    dialogo._adicionar_membro()
    atual = next(c for c in ESTADO["cartoes"] if c["id"] == 12)
    assert any(m["usuario_id"] == 1 for m in atual["membros"])

    # Reabre com o estado atualizado e remove o membro recém-adicionado.
    dialogo2 = DialogoCartao(api, cartao=copy.deepcopy(atual), usuarios=copy.deepcopy(_USUARIOS))
    item = next(
        dialogo2._membros.item(i)
        for i in range(dialogo2._membros.count())
        if dialogo2._membros.item(i).data(Qt.ItemDataRole.UserRole) == 1
    )
    dialogo2._membros.setCurrentItem(item)
    dialogo2._remover_membro()
    final = next(c for c in ESTADO["cartoes"] if c["id"] == 12)
    assert not any(m["usuario_id"] == 1 for m in final["membros"])


def test_dialogo_modo_leitura_desabilita_salvar():
    api = _api()
    cartao = copy.deepcopy(ESTADO["cartoes"][0])
    dialogo = DialogoCartao(api, modo_leitura=True, cartao=cartao, usuarios=[])
    assert dialogo._btn_salvar.isEnabled() is False


# --------------------------------------------------------------- listas

def test_dialogo_listas_cria_e_renomeia():
    api = _api()
    dialogo = DialogoListas(api, listas=copy.deepcopy(_LISTAS), admin=True)
    dialogo._nome.setText("Revisão")
    dialogo._btn_nova.click()
    assert any(l["nome"] == "Revisão" for l in ESTADO["listas"])

    dialogo._lista.setCurrentRow(0)
    dialogo._nome.setText("Orçamentos")
    dialogo._btn_renomear.click()
    assert ESTADO["listas"][0]["nome"] == "Orçamentos"


def test_dialogo_listas_excluir_so_para_admin():
    assert DialogoListas(_api(), listas=[], admin=True)._btn_excluir.isHidden() is False
    assert DialogoListas(_api(), listas=[], admin=False)._btn_excluir.isHidden() is True


def test_dialogo_listas_arquiva(monkeypatch):
    api = _api()
    dialogo = DialogoListas(api, listas=copy.deepcopy(_LISTAS), admin=True)
    dialogo._lista.setCurrentRow(2)
    dialogo._btn_arquivar.click()
    assert next(l for l in ESTADO["listas"] if l["id"] == 3)["arquivada"] is True
