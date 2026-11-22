"""Testes da página Cadastro de Produtos & Serviços (mockup 2.2)."""

from __future__ import annotations

import json

import json as _json

import httpx
from PySide6.QtWidgets import QPushButton

from printgest.core.api import Api
from printgest.ui.modulos.produtos import PaginaProdutos

_PRODUTOS = [
    {
        "id": 1,
        "codigo": "00001",
        "nome": "Papel A4 75g Resma",
        "tipo": "produto",
        "categoria_id": 2,
        "unidade": "un",
        "preco_venda": "38.50",
        "preco_custo": "22.00",
    },
    {
        "id": 2,
        "codigo": "00002",
        "nome": "Impressão 4x4 (1000 u.)",
        "tipo": "servico",
        "categoria_id": None,
        "unidade": "un",
        "preco_venda": "184.70",
        "preco_custo": "84.70",
    },
]

_CATEGORIAS = [
    {"id": 1, "nome": "Papéis & Gramaturas"},
    {"id": 2, "nome": "Suprimentos"},
    {"id": 3, "nome": "Acabamento"},
]

_GETS: list[httpx.Request] = []
_ESCRITAS: list[tuple[str, str, str]] = []


def _handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/produtos":
        _GETS.append(request)
        return httpx.Response(
            200,
            json={"data": _PRODUTOS, "meta": {"total": len(_PRODUTOS), "limit": 50, "offset": 0}},
        )
    if request.method == "GET" and request.url.path == "/v1/categorias":
        return httpx.Response(
            200,
            json={"data": _CATEGORIAS, "meta": {"total": len(_CATEGORIAS), "limit": 1000, "offset": 0}},
        )
    if request.method == "POST" and request.url.path == "/v1/produtos":
        _ESCRITAS.append(("POST", "", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 3, "nome": "Novo"}})
    if request.method == "POST" and request.url.path == "/v1/produtos/variacoes/gerar":
        corpo = request.read().decode()
        _ESCRITAS.append(("GERAR", "variacoes", corpo))
        filhas = [
            {"id": 90 + i, "sku": f"VAR-{i}", "nome": f"Variante {i}"}
            for i in range(len(json.loads(corpo)["variacoes"]))
        ]
        return httpx.Response(201, json={"data": filhas})
    if request.method == "PUT" and request.url.path == "/v1/produtos/1":
        _ESCRITAS.append(("PUT", "1", request.read().decode()))
        return httpx.Response(200, json={"data": {"id": 1, "nome": "Alterado"}})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _pagina(modo_leitura: bool = False):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return PaginaProdutos(api, modo_leitura=modo_leitura)


def test_carrega_grade_e_categorias(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pumpar(lambda: pagina._categoria.widget.count() == 3)
    assert "de 2 registros" in pagina._paginador._info.text()
    assert "Papel A4" in pagina._tabela.item(0, 2).text()
    assert pagina._tabela.item(0, 5).text() == "R$ 38,50"
    assert pagina._nomes_cat.get(2) == "Suprimentos"


def test_selecionar_linha_preenche_formulario(app, pumpar):
    _GETS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pumpar(lambda: pagina._categoria.widget.count() == 3)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    assert pagina._nome.valor() == "Papel A4 75g Resma"
    assert pagina._codigo.valor() == "00001"
    assert pagina._categoria.valor() == 2
    assert pagina._preco_venda.valor() is not None


def test_criar_novo_aplica_padroes_e_envia_post(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pumpar(lambda: pagina._categoria.widget.count() == 3)
    pagina._btn_novo.click()
    assert pagina._editando_id is None
    assert pagina._tipo.valor() == "produto"
    assert pagina._controla.valor() is True
    assert pagina._unidade.valor() == "un"
    pagina._codigo.definir("00009")
    pagina._nome.definir("Papel Couché 115g")
    pagina._categoria.definir(3)
    pagina._preco_venda.definir("12,90")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "POST" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("POST", "")
    enviado = json.loads(corpo)
    assert enviado["codigo"] == "00009"
    assert enviado["nome"] == "Papel Couché 115g"
    assert enviado["categoria_id"] == 3
    assert float(enviado["preco_venda"].replace(",", ".")) == 12.9
    assert enviado["controla_estoque"] is True
    assert enviado["tipo"] == "produto"


def test_salvar_existente_envia_put(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    pumpar(lambda: pagina._editando_id == 1)
    pagina._nome.definir("Papel A4 75g Resma (2ª face)")
    pagina._btn_salvar.click()
    pumpar(lambda: any(escr[0] == "PUT" for escr in _ESCRITAS))

    metodo, item, corpo = _ESCRITAS[-1]
    assert (metodo, item) == ("PUT", "1")
    enviado = json.loads(corpo)
    assert enviado["nome"] == "Papel A4 75g Resma (2ª face)"
    assert enviado["categoria_id"] == 2


def test_modo_leitura_nao_salva(app, pumpar):
    _GETS.clear()
    _ESCRITAS.clear()
    pagina = _pagina(modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina._btn_salvar.isEnabled() is False
    pagina._btn_salvar.click()
    assert _ESCRITAS == []

def test_variacoes_gera_e_atualiza_cache():
    import httpx as _httpx

    from printgest.core.api import Api

    chamadas = []

    def handler(request):
        if request.url.path == "/v1/produtos/variacoes/gerar":
            chamadas.append(_json.loads(request.content or b"{}"))
            return _httpx.Response(
                201,
                json={
                    "data": [
                        {
                            "id": 90,
                            "sku": "CAR-M-X-AZUL",
                            "uuid": "abc",
                            "codigo": "CAR-M-X-AZUL-1",
                            "nome": "Carimbo M X Azul",
                        }
                    ]
                },
            )
        if request.url.path == "/v1/produtos":
            return _httpx.Response(200, json={"data": [], "meta": {"total": 0}})
        return _httpx.Response(404, json={"detail": "x"})

    api = Api(base_url="http://daemon.test", transport=_httpx.MockTransport(handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1}})
    r = api.gerar_variacoes(
        {
            "produto_pai_id": 1,
            "prefixo_sku": "CAR",
            "variacoes": [{"tamanho": "M", "marca": "X", "cor": "Azul"}],
        }
    )
    assert r[0]["sku"] == "CAR-M-X-AZUL"
    assert chamadas[0]["produto_pai_id"] == 1


def test_buscar_sku_no_cliente():
    import httpx as _httpx

    def handler(request):
        if request.url.path.startswith("/v1/produtos/buscar-sku/"):
            return _httpx.Response(200, json={"data": {"id": 7, "sku": "CAR-M-X-AZUL"}})
        return _httpx.Response(404, json={"detail": "x"})

    from printgest.core.api import Api

    a = Api(base_url="http://daemon.test", transport=_httpx.MockTransport(handler))
    a.autenticar({"token": "tok", "usuario": {"id": 1}})
    assert a.buscar_sku("CAR-M-X-AZUL")["sku"] == "CAR-M-X-AZUL"


def test_servicos_nao_oferecem_gerar_variacoes(app):
    """Serviço não tem estoque — o botão não deve aparecer."""
    from printgest.ui.modulos.produtos import PaginaServicos

    pagina = PaginaServicos(_pagina()._api)
    assert not any(b.text() == "Gerar variações" for b in pagina.findChildren(QPushButton))


def test_botao_gerar_variacoes_envia_payload_e_usa_contagem_real(app, pumpar, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox
    from printgest.ui.modulos import produtos as produtos_mod

    class DialogoFalso:
        DialogCode = QDialog.DialogCode

        def __init__(self, **_kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def valor(self):
            return [{"tamanho": "M", "marca": "X", "cor": "Azul"}]

    monkeypatch.setattr(produtos_mod, "DialogoVariacoes", DialogoFalso)
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.Yes,
    )
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    mensagens = []
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda _pai, titulo, texto, *_a, **_k: mensagens.append(texto),
    )

    pagina._btn_variacoes.click()
    pumpar(lambda: any(e[0] == "GERAR" for e in _ESCRITAS))

    corpo = json.loads(next(e[2] for e in _ESCRITAS if e[0] == "GERAR"))
    assert corpo["produto_pai_id"] == 1
    assert corpo["variacoes"] == [{"tamanho": "M", "marca": "X", "cor": "Azul"}]
    assert any("1 variante(s) criada(s)" in m for m in mensagens)
    assert pagina._btn_variacoes.isEnabled()


def test_variacao_sem_atributo_nao_chama_api(app, pumpar, monkeypatch):
    from PySide6.QtWidgets import QDialog
    from printgest.ui.modulos import produtos as produtos_mod

    class DialogoVazio:
        DialogCode = QDialog.DialogCode

        def __init__(self, **_kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

        def valor(self):
            return []

    monkeypatch.setattr(produtos_mod, "DialogoVariacoes", DialogoVazio)
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    antes = len(_ESCRITAS)
    pagina._btn_variacoes.click()
    assert len(_ESCRITAS) == antes


def test_secoes_colocam_preco_e_estoque_antes_das_fotos(app):
    pagina = _pagina()
    titulos = [titulo for titulo, _campos in pagina._lista_secoes]
    assert titulos == [
        "Cadastro", "Precificação", "Estoque", "Variação (filha)", "Imagens"
    ]
    imagens = [
        campos for titulo, campos in pagina._lista_secoes if titulo == "Imagens"
    ]
    assert imagens == [[pagina._foto1, pagina._foto2]]


def test_coluna_ref_tem_largura_para_o_numero(app, pumpar):
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert pagina.PESOS[0] >= 2
    assert pagina._tabela.columnWidth(0) >= 56


def test_botao_variacoes_so_habilitado_com_produto_selecionado(app, pumpar):
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    assert not pagina._btn_variacoes.isEnabled()
    pagina._tabela.selectRow(0)
    app.processEvents()
    assert pagina._btn_variacoes.isEnabled()


def test_dialogo_variacoes_sugere_dominios_do_catalogo(app, pumpar, monkeypatch):
    from PySide6.QtWidgets import QDialog, QMessageBox
    from printgest.ui.modulos import produtos as produtos_mod

    capturado: dict = {}

    class DialogoFalso:
        DialogCode = QDialog.DialogCode

        def __init__(self, **kwargs):
            capturado.update(kwargs)

        def exec(self):
            return QDialog.DialogCode.Rejected

        def valor(self):
            return []

    monkeypatch.setattr(produtos_mod, "DialogoVariacoes", DialogoFalso)
    pagina = _pagina()
    pumpar(lambda: pagina._tabela.rowCount() == 2)
    pagina._tabela.selectRow(0)
    monkeypatch.setattr(
        pagina._api,
        "listar",
        lambda *_a, **_k: {
            "data": [
                {"atrib_tamanho": "M", "atrib_marca": "Marca X", "atrib_cor": "Azul"},
                {"atrib_tamanho": "G", "atrib_marca": "Marca X", "atrib_cor": "Preto"},
            ],
            "total": 2,
        },
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: None)

    pagina._btn_variacoes.click()
    assert capturado["dominios"] == {
        "tamanho": ["G", "M"], "marca": ["Marca X"], "cor": ["Azul", "Preto"]
    }
    assert capturado["produto_pai"]["id"] == 1
"""Testes do diálogo estruturado de variações e da distinção pai/filha."""


def test_preview_sku_dedupe_e_remocao(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from printgest.ui.modulos.dialogo_variacoes import DialogoVariacoes

    avisos = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda _pai, titulo, texto, *_a, **_k: avisos.append(texto),
    )
    dialogo = DialogoVariacoes(
        {"codigo": "cv01"},
        {"tamanho": ["M"], "marca": ["Marca X"], "cor": ["Azul"]},
    )
    assert dialogo._prefixo == "CV01"
    dialogo._campos["tamanho"].setCurrentText("M")
    dialogo._campos["marca"].setCurrentText("Marca X")
    dialogo._campos["cor"].setCurrentText("Azul")
    dialogo._adicionar()

    assert dialogo.valor() == [{"tamanho": "M", "marca": "Marca X", "cor": "Azul"}]
    assert dialogo._lista.item(0).toolTip() == "CV01-M-MARCAX-AZUL"
    assert dialogo._ok.isEnabled()

    dialogo._adicionar()  # repetida: não duplica
    assert dialogo._lista.count() == 1
    assert avisos

    dialogo._lista.setCurrentRow(0)
    dialogo._remover()
    assert dialogo._lista.count() == 0
    assert not dialogo._ok.isEnabled()


def test_dialogo_exige_ao_menos_um_atributo(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from printgest.ui.modulos.dialogo_variacoes import DialogoVariacoes

    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: None)
    dialogo = DialogoVariacoes({"codigo": "cv01"})
    dialogo._adicionar()
    assert dialogo.valor() == []
    assert not dialogo._ok.isEnabled()


def test_filtro_variacoes_e_marcador_na_grade(app, monkeypatch):
    pagina = _pagina()
    capturado: dict = {}

    def falso_listar(entidade, **kwargs):
        capturado.update(kwargs)
        return {"data": [], "total": 0, "limit": 50, "offset": 0}

    monkeypatch.setattr(pagina._api, "listar_com_filtros", falso_listar)
    pagina._filtro = "variante"
    pagina._listar("", 0, {})
    assert capturado["somente_variantes"] is True
    assert "tipo" not in capturado

    filha = {"id": 2, "tipo": "produto", "nome": "Filha", "produto_pai_id": 1}
    pai = {"id": 1, "tipo": "produto", "nome": "Pai", "produto_pai_id": None}
    assert pagina._formatar_texto(filha, "nome") == "↳ Filha"
    assert pagina._formatar_texto(pai, "nome") == "Pai"


def test_formulario_variante_mostra_pai_sku_e_atributos(app):
    pagina = _pagina()
    pagina._preencher_campos({
        "id": 9,
        "codigo": "CV01-M-MARCAX-AZUL-a1b2c3d4",
        "nome": "Cartão de visita M Marca X Azul",
        "tipo": "produto",
        "unidade": "un",
        "preco_venda": "120.00",
        "produto_pai_id": 1,
        "sku": "CV01-M-MARCAX-AZUL",
        "uuid": "abc-123",
        "atrib_tamanho": "M",
        "atrib_marca": "Marca X",
        "atrib_cor": "Azul",
    })
    assert pagina._pai_id.valor() == "#1"
    assert not pagina._pai_id.widget.isEnabled()
    assert pagina._sku.valor() == "CV01-M-MARCAX-AZUL"
    assert not pagina._sku.widget.isEnabled()
    assert pagina._atrib_tamanho.valor() == "M"
    assert pagina._atrib_tamanho.widget.isEnabled()

    dados = pagina._payload()
    assert dados["atrib_tamanho"] == "M"
    assert dados["atrib_marca"] == "Marca X"
    assert dados["atrib_cor"] == "Azul"
    assert "sku" not in dados and "produto_pai_id" not in dados


def test_dialogo_variacoes_inclui_preco_e_barras(app, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from printgest.ui.modulos.dialogo_variacoes import DialogoVariacoes

    monkeypatch.setattr(QMessageBox, "warning", lambda *_a, **_k: None)
    dialogo = DialogoVariacoes({"codigo": "cv01"})
    dialogo._campos["tamanho"].setCurrentText("M")
    dialogo._preco.setText("10,50")
    dialogo._barras.setText("7891000100103")
    dialogo._adicionar()

    dados = dialogo.valor()[0]
    assert dados["preco_venda"] == "10.50"
    assert dados["codigo_barras"] == "7891000100103"
