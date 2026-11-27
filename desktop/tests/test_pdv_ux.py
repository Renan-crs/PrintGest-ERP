"""Melhorias UX do PDV: toggles, split, offline e destaque de ações."""

from __future__ import annotations

import httpx
from PySide6.QtWidgets import QLabel

from printgest.core.api import Api
from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao

_PRODUTOS = [
    {"id": 5, "codigo": "B015", "nome": "Adesivo", "preco_venda": "100.00",
     "tipo": "produto", "controla_estoque": False},
]
_ESCRITAS: list[dict] = []


def _handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if p.startswith("/v1/produtos") and request.method == "GET":
        return httpx.Response(
            200, json={
                "data": _PRODUTOS, "meta": {"total": 1, "limit": 50, "offset": 0}
            }
        )
    if p == "/v1/vendas" and request.method == "POST":
        import json
        _ESCRITAS.append(json.loads(request.content))
        return httpx.Response(200, json={"data": {"id": 11, "numero": 2895}})
    if p.startswith("/v1/financeiro/caixa"):
        return httpx.Response(200, json={"data": None})
    if p.startswith("/v1/vendas") and request.method == "GET":
        return httpx.Response(
            200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
        )
    if p.startswith("/v1/clientes"):
        return httpx.Response(
            200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
        )
    return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})


def _pagina():
    _ESCRITAS.clear()
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar(
        {"token": "t", "usuario": {"id": 1, "nome": "Admin", "login": "admin",
                                   "nivel_acesso": "admin"}}
    )
    return PaginaVendaBalcao(api, nivel="admin")


def test_toggles_de_forma_de_pagamento(app):
    pagina = _pagina()
    assert len(pagina._toggles_forma) == 6
    pagina._toggles_forma["pix"].click()
    assert pagina._forma.valor() == "pix"
    assert pagina._toggles_forma["pix"].isChecked()


def _carregar_catalogo(editor) -> None:
    editor._produtos_recebidos({"data": _PRODUTOS})


def test_payload_com_split_pagamento(app):
    pagina = _pagina()
    editor = pagina._itens_editor
    _carregar_catalogo(editor)
    editor._entrada.setText("B015")
    editor._adicionar_pela_busca()
    assert abs(pagina._total_venda - 100) < 0.01

    pagina._btn_adicionar_pagamento.click()
    registro = pagina._linhas_pagamento[0]
    registro["combo"].setCurrentIndex(registro["combo"].findData("pix"))
    registro["valor"].definir("40,00")

    payload = pagina._payload()
    assert payload["forma_pagamento"] == "dinheiro"
    assert [(p["forma_pagamento"], p["valor"]) for p in payload["pagamentos"]] == [
        ("dinheiro", "60.00"), ("pix", "40.00")
    ]


def test_indicador_offline_no_pdv(app):
    pagina = _pagina()
    pagina._pintar_conexao_pdv(False)
    assert "offline" in pagina._lbl_conexao_pdv.text().lower()
    pagina._pintar_conexao_pdv(True)
    assert "online" in pagina._lbl_conexao_pdv.text().lower()


def test_finalizar_acende_com_item(app):
    pagina = _pagina()
    editor = pagina._itens_editor
    _carregar_catalogo(editor)
    editor._entrada.setText("B015")
    editor._adicionar_pela_busca()
    assert pagina._btn_salvar.property("destaque") is True


def test_elementos_visuais_de_toque(app):
    pagina = _pagina()
    editor = pagina._itens_editor
    assert editor._btn_avulso.objectName() == "itemAvulso"
    assert editor.findChild(QLabel, "lupaBusca") is not None
    # Linha de item: botão de remover com alvo de 40 px.
    _carregar_catalogo(editor)
    editor._entrada.setText("B015")
    editor._adicionar_pela_busca()
    remover = [
        b for b in editor._tabela.findChildren(type(editor._btn_avulso))
        if b.accessibleName() == "Remover item"
    ]
    assert remover and remover[0].width() == 40


def test_explicacao_da_regra_aparece_apos_salvar(app):
    pagina = _pagina()
    pagina._salvo(
        {
            "id": 11, "numero": 2895,
            "itens": [{"explicacao": ["Faixa 50-199: R$ 0,80"]}],
        },
        False,
    )
    assert not pagina._lbl_regra.isHidden()
    assert "Faixa 50-199" in pagina._lbl_regra.text()
