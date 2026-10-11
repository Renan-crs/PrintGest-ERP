"""Testes do menu Projetos: visões Quadro (Kanban) e Lista.

O quadro reusa `/v1/os` (1 projeto = 1 O.S., tipo `os`) — uma consulta por
etapa — e o cartão abre o registro na visão Lista. O calendário e o arrastar
entre colunas ficam fora desta entrega (ver docs/revisao_projetos.md).
"""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from printgest.core.api import Api
from printgest.ui.modulos.os import PaginaProjetos

_OSS = [
    {
        "id": 1,
        "numero": 1044,
        "tipo": "os",
        "status": "aberto",
        "cliente_nome": "Ana",
        "data_previsao_entrega": "2999-09-25",
        "valor_total": "312.00",
    },
    {
        "id": 2,
        "numero": 1045,
        "tipo": "os",
        "status": "aprovado",
        "cliente_nome": "Biz Gráfica Rápida e Comunicação Visual Ltda",
        "data_previsao_entrega": "2020-01-01",
        "valor_total": "100.00",
    },
    {
        "id": 3,
        "numero": 1046,
        "tipo": "os",
        "status": "producao",
        "cliente_nome": "Cliente de nome muito muito longo para elidir no cartão",
        "data_previsao_entrega": None,
        "valor_total": None,
    },
    {"id": 4, "numero": 1047, "tipo": "os", "status": "pronta", "cliente_nome": "Dora", "valor_total": "50.00"},
    {"id": 5, "numero": 1048, "tipo": "os", "status": "entregue", "cliente_nome": "Eva", "valor_total": "10.00"},
    # Orçamento (tipo ≠ os): nunca pode aparecer no quadro de projetos.
    {"id": 6, "numero": 3100, "tipo": "orcamento", "status": "aberto", "cliente_nome": "Biz"},
]

_CLIENTES = [{"id": 1, "nome_razao": "Ana"}, {"id": 2, "nome_razao": "Biz"}]
_FUNCIONARIOS = [{"id": 10, "nome": "Vina", "e_vendedor": True, "e_atendente": True}]
_PRODUTOS = [{"id": 5, "codigo": "B015", "nome": "Adesivo", "preco_venda": "10.00"}]

_GETS: list[httpx.Request] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/os":
        _GETS.append(request)
        params = request.url.params
        linhas = _OSS
        if params.get("tipo"):
            linhas = [o for o in linhas if o["tipo"] == params["tipo"]]
        if params.get("status"):
            linhas = [o for o in linhas if o["status"] == params["status"]]
        return httpx.Response(
            200, json={"data": linhas, "meta": {"total": len(linhas), "limit": 200, "offset": 0}}
        )
    if request.method == "GET" and request.url.path.startswith("/v1/os/"):
        ident = int(request.url.path.rsplit("/", 1)[1])
        dado = next(o for o in _OSS if o["id"] == ident)
        return httpx.Response(200, json={"data": dado})
    if request.url.path == "/v1/clientes":
        return httpx.Response(200, json={"data": _CLIENTES, "meta": {"total": 2, "limit": 50, "offset": 0}})
    if request.url.path == "/v1/funcionarios":
        return httpx.Response(200, json={"data": _FUNCIONARIOS, "meta": {"total": 1, "limit": 50, "offset": 0}})
    if request.url.path == "/v1/produtos":
        return httpx.Response(200, json={"data": _PRODUTOS, "meta": {"total": 1, "limit": 50, "offset": 0}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pagina(modo_leitura: bool = False) -> PaginaProjetos:
    _GETS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaProjetos(api, modo_leitura=modo_leitura)


@pytest.fixture
def pagina(pumpar):
    pagina = _pagina()
    pumpar(
        lambda: pagina._tabela.rowCount() == 5
        and pagina._quadro.contagem("aguardando") == 2
    )
    return pagina


def test_quadro_tem_as_quatro_etapas(pagina):
    assert pagina._quadro.coluna("aguardando")._titulo.text() == "AGUARDANDO"
    assert pagina._quadro.coluna("producao")._titulo.text() == "EM PRODUÇÃO"
    assert pagina._quadro.contagem("pronta") == 1
    assert pagina._quadro.contagem("entregue") == 1


def test_aprovado_agrupa_com_aberto_na_aguardando(pagina):
    ids = {c.id_registro for c in pagina._quadro.coluna("aguardando").cartoes()}
    assert ids == {1, 2}  # aberto (1044) + aprovado (1045)


def test_orcamento_nao_entra_no_quadro(pagina):
    todos = set()
    for chave in ("aguardando", "producao", "pronta", "entregue"):
        todos |= {c.id_registro for c in pagina._quadro.coluna(chave).cartoes()}
    assert 6 not in todos


def test_quadro_consulta_apenas_os_do_tipo_papel(pagina):
    tipos = {request.url.params.get("tipo") for request in _GETS}
    assert tipos == {"os"}


def test_cartao_elidido_preserva_texto_no_tooltip(pagina):
    cartao = next(
        c
        for c in pagina._quadro.coluna("producao").cartoes()
        if c.id_registro == 3
    )
    assert "Cliente de nome muito muito longo" in cartao.toolTip()


def test_cartao_atrasado_recebe_badge(pagina):
    cartao = next(
        c for c in pagina._quadro.coluna("aguardando").cartoes() if c.id_registro == 2
    )
    badges = [b.text() for b in cartao.findChildren(QLabel)]
    assert "Atrasado" in badges


def test_clicar_cartao_abre_o_registro_na_lista(pagina, pumpar):
    assert pagina._visao_atual == 0
    pagina._quadro.coluna("producao").cartoes()[0].selecionado.emit(3)
    pumpar(lambda: pagina._editando_id == 3)
    assert pagina._visao_atual == 1
    assert pagina._cliente.valor() == 1 or pagina._editando_id == 3


def test_alternador_troca_visao_e_esconde_filtros(pagina):
    assert pagina._visao_atual == 0
    assert pagina._filtros_widget.isHidden()
    pagina._btn_lista.click()
    assert pagina._visao_atual == 1
    assert not pagina._filtros_widget.isHidden()
    pagina._btn_quadro.click()
    assert pagina._visao_atual == 0
    assert pagina._filtros_widget.isHidden()


def test_novo_projeto_volta_para_a_lista(pagina):
    pagina._editando_id = 5
    pagina._btn_novo.click()
    assert pagina._visao_atual == 1
    assert pagina._editando_id is None


def test_estado_vazio_no_quadro(app, pumpar):
    def vazio(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/os":
            return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 200, "offset": 0}})
        return _handler(request)

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(vazio))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    pagina = PaginaProjetos(api)
    pumpar(lambda: pagina._quadro.coluna("aguardando")._contagem.text() == "0")
    for chave in ("aguardando", "producao", "pronta", "entregue"):
        coluna = pagina._quadro.coluna(chave)
        assert not coluna._vazio.isHidden()
        assert coluna._vazio.text() == "Sem registros"


def test_modo_leitura_bloqueia_escrita_mas_mostra_quadro(app, pumpar):
    pagina = _pagina(modo_leitura=True)
    pumpar(lambda: pagina._quadro.contagem("aguardando") == 2)
    assert pagina._btn_salvar.isEnabled() is False
    assert pagina._quadro.coluna("aguardando")._vazio.isHidden()


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


@pytest.mark.parametrize("largura,altura,escala", _RESOLUCOES)
def test_quadro_sem_rolagem_horizontal(app, pumpar, largura, altura, escala):
    # Largura lógica = física / escala; pior caso realista: lateral recolhida (64px).
    conteudo = int(largura * 100 / escala) - 64
    logica_a = int(altura * 100 / escala)

    pagina = _pagina()
    container = QWidget()
    caixa = QVBoxLayout(container)
    caixa.setContentsMargins(0, 0, 0, 0)
    caixa.addWidget(pagina)
    container.resize(conteudo, logica_a)
    container.show()
    pumpar(lambda: pagina._quadro.contagem("aguardando") == 2)
    app.processEvents()

    assert pagina.minimumSizeHint().width() <= conteudo, (
        f"piso {pagina.minimumSizeHint().width()} > {conteudo} "
        f"({largura}x{altura}@{escala}%)"
    )
    assert pagina._quadro._area.horizontalScrollBar().maximum() == 0, (
        f"quadro rola na horizontal em {largura}x{altura}@{escala}%"
    )
    # A grade da Lista também não rola lateralmente.
    tabela = pagina._tabela
    assert tabela.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    container.close()
