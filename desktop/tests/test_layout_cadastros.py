"""Regressão de layout das telas de cadastro (sem rolagem horizontal).

Roda a Tela Principal (offscreen) em 1280x720, 1366x768 e 1920x1080 nas escalas
100%/125%/150% — cada par vira a largura lógica correspondente — e verifica:

  - nenhuma grade de cadastro rola na horizontal (colunas == viewport);
  - o painel do formulário não rola na horizontal;
  - o estado vazio aparece quando a lista está vazia;
  - o campo usa rótulo acima do controle e a grade tem 2 colunas iguais.
"""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from printgest.core.api import Api
from printgest.ui.modulos import criar_pagina
from printgest.ui.modulos.clientes import PaginaClientes
from printgest.ui.modulos.fornecedores import PaginaFornecedores
from printgest.ui.modulos.produtos import PaginaProdutos, PaginaServicos
from printgest.ui.tela_principal import TelaPrincipal

# (largura física, altura física, escala Windows) → largura lógica = física/escala
_RESOLUCOES = [
    (1280, 720, 100),
    (1280, 720, 125),
    (1280, 720, 150),
    (1366, 768, 100),
    (1366, 768, 125),
    (1366, 768, 150),
    (1920, 1080, 100),
    (1920, 1080, 125),
    (1920, 1080, 150),
]

_PAGINAS = {
    "cliente": PaginaClientes,
    "fornecedor": PaginaFornecedores,
    "produto": PaginaProdutos,
    "servico": PaginaServicos,
}

_CLIENTE = {
    "id": 1,
    "nome_razao": "Cliente com razão social extremamente longa ltda ME",
    "tipo_pessoa": "pj",
    "cpf_cnpj": "18.234.901/0001-44",
}
_PRODUTO = {
    "id": 1,
    "codigo": "INS-0209",
    "nome": "Lâmpada LED tubular 120cm 18W branca fria",
    "tipo": "produto",
    "preco_venda": "123456.78",
}


def _handler(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path
    if caminho == "/v1/licenca":
        return httpx.Response(
            200, json={"data": {"status": "ativa", "modo_leitura": False}}
        )
    if caminho == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if caminho == "/v1/dashboard/resumo":
        return httpx.Response(
            200,
            json={
                "data": {
                    "filial_nome": "Matriz",
                    "vendas_hoje_qtd": 0,
                    "vendas_hoje_valor": "0",
                    "vendas_ontem_qtd": 0,
                    "vendas_ontem_valor": "0",
                    "projetos_em_producao": 0,
                    "projetos_atrasados": 0,
                    "a_receber_vence_hoje": "0",
                    "a_receber_atrasado": "0",
                    "estoque_abaixo_minimo": 0,
                    "entregas_hoje": [],
                    "vendas_7_dias": [],
                    "faturamento_previsto": [],
                }
            },
        )
    if caminho == "/v1/produtos":
        return httpx.Response(
            200, json={"data": [_PRODUTO], "meta": {"total": 1, "limit": 50, "offset": 0}}
        )
    if caminho == "/v1/categorias":
        return httpx.Response(
            200, json={"data": [{"id": 2, "nome": "Suprimentos"}], "meta": {"total": 1}}
        )
    if caminho == "/v1/clientes":
        return httpx.Response(
            200, json={"data": [_CLIENTE], "meta": {"total": 1, "limit": 50, "offset": 0}}
        )
    return httpx.Response(
        200, json={"data": [_CLIENTE], "meta": {"total": 1, "limit": 50, "offset": 0}}
    )


def _principal() -> TelaPrincipal:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar(
        {
            "token": "tok",
            "usuario": {
                "id": 1,
                "nome": "Ana",
                "login": "ana",
                "nivel_acesso": "admin",
                "filial_nome": "Matriz",
            },
        }
    )
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    principal.setMinimumSize(0, 0)
    return principal


def _criar(item_id: str):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar(
        {
            "token": "tok",
            "usuario": {
                "id": 1,
                "nome": "Ana",
                "login": "ana",
                "nivel_acesso": "admin",
                "filial_nome": "Matriz",
            },
        }
    )
    return criar_pagina(item_id, item_id, api, False, "admin")


@pytest.mark.parametrize("largura,altura,escala", _RESOLUCOES)
def test_cadastros_sem_rolagem_horizontal(app, pumpar, largura, altura, escala):
    # Largura lógica = física / escala. Pior caso realista: lateral recolhida
    # (64px), que é o que permite caber em 150%.
    logica_l = int(largura * 100 / escala)
    logica_a = int(altura * 100 / escala)
    conteudo = logica_l - 64

    for item_id in _PAGINAS:
        pagina = _criar(item_id)
        container = QWidget()
        caixa = QVBoxLayout(container)
        caixa.setContentsMargins(0, 0, 0, 0)
        caixa.addWidget(pagina)
        container.resize(conteudo, logica_a)
        container.show()
        pumpar(lambda p=pagina: p._total == 1)
        app.processEvents()

        assert pagina.minimumSizeHint().width() <= conteudo, (
            f"{item_id}: piso {pagina.minimumSizeHint().width()} > {conteudo} "
            f"({largura}x{altura}@{escala}%)"
        )

        tabela = pagina._tabela
        assert (
            tabela.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert (
            pagina._painel_form.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        visiveis = [
            c for c in range(tabela.columnCount()) if not tabela.isColumnHidden(c)
        ]
        assert visiveis, item_id
        colunas = sum(tabela.columnWidth(c) for c in visiveis)
        assert colunas <= tabela.viewport().width() + 2, (
            f"{item_id}: colunas {colunas} > viewport {tabela.viewport().width()} "
            f"({largura}x{altura}@{escala}%)"
        )
        container.close()


def test_estado_vazio_aparece_quando_lista_vazia(app, pumpar):
    def handler(_request: httpx.Request) -> httpx.Response:
        caminho = _request.url.path
        if caminho == "/v1/licenca":
            return httpx.Response(
                200, json={"data": {"status": "ativa", "modo_leitura": False}}
            )
        if caminho == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if caminho == "/v1/dashboard/resumo":
            return _handler(_request)
        return httpx.Response(
            200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
        )

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    api.autenticar(
        {
            "token": "tok",
            "usuario": {
                "id": 1,
                "nome": "Ana",
                "login": "ana",
                "nivel_acesso": "admin",
            },
        }
    )
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    principal.setMinimumSize(0, 0)
    principal.resize(1280, 720)
    principal.show()
    principal._navegar("cliente")
    pagina = principal._paginas["cliente"]
    pumpar(lambda: pagina._total == 0)
    app.processEvents()
    assert not pagina._tabela._vazio.isHidden()
    assert "Novo Cliente" in pagina._tabela._vazio.text()
    principal.close()


def test_campo_com_rotulo_acima_e_data_sem_padrao(app, pumpar):
    principal = _principal()
    principal._navegar("cliente")
    pagina = principal._paginas["cliente"]
    app.processEvents()

    celula = pagina._nome._celula
    layout = celula.layout()
    assert isinstance(layout, QVBoxLayout)
    rotulo = layout.itemAt(0).widget()
    assert isinstance(rotulo, QLabel)
    assert layout.itemAt(1).widget() is pagina._nome.widget

    # Campos longos ocupam as 2 colunas; curtos ficam em 1.
    assert pagina._nome.largo is True
    assert pagina._doc.largo is False

    # Data de nascimento começa "sem data" (NULL), nunca 01/01/1900.
    assert pagina._nasc.valor() is None
    assert not pagina._nasc._data.isEnabled()


def test_mascara_acompanha_tipo_de_pessoa(app, pumpar):
    principal = _principal()
    principal._navegar("cliente")
    pagina = principal._paginas["cliente"]
    app.processEvents()

    pagina._tipo.definir("pf")
    assert pagina._doc._edicao.inputMask() == "000.000.000-00;_"
    pagina._tipo.definir("pj")
    assert pagina._doc._edicao.inputMask() == "00.000.000/0000-00;_"


def test_atalhos_do_cadastro(app, pumpar):
    from PySide6.QtGui import QShortcut

    principal = _principal()
    principal._navegar("cliente")
    pagina = principal._paginas["cliente"]
    app.processEvents()

    atalhos = {
        atalho.key().toString(): atalho for atalho in pagina.findChildren(QShortcut)
    }
    assert {"F6", "F10", "Esc"} <= set(atalhos)

    # F6 abre um cadastro em branco...
    pagina._editando_id = 7
    pagina._form_titulo.setText("Editando #00007")
    atalhos["F6"].activated.emit()
    assert pagina._editando_id is None
    assert pagina._form_titulo.text() == pagina.ROTULO_NOVO

    # ...e Esc cancela uma edição em andamento.
    pagina._editando_id = 7
    atalhos["Esc"].activated.emit()
    assert pagina._editando_id is None


def test_operador_nao_edita_precos_de_produto(app, pumpar):
    """RBAC: operador consulta o catálogo, mas os preços ficam desabilitados."""
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar(
        {
            "token": "tok",
            "usuario": {
                "id": 2,
                "nome": "Op",
                "login": "op",
                "nivel_acesso": "operador",
            },
        }
    )
    pagina = PaginaProdutos(api, nivel="operador")
    app.processEvents()
    assert not pagina._preco_custo._edicao.isEnabled()
    assert not pagina._preco_venda._edicao.isEnabled()
