"""Testes do módulo Fiscal: host de abas, Documentos Fiscais (consulta) e
Contingência (aviso de gateway + pendências).

A emissão exige gateway externo (inexistente), então o módulo é somente leitura;
o backend real é coberto por `backend/tests/test_fiscal.py`. Aqui um
`MockTransport` emula documentos/resumo para exercitar a UI sem servidor.
"""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QMessageBox

from printgest.core.api import Api
from printgest.ui.modulos.fiscal import (
    PaginaContingencia,
    PaginaDocumentosFiscais,
    PaginaFiscal,
)

DOC_AUTORIZADO = {
    "id": 1,
    "filial_id": 1,
    "modelo": "nfe",
    "numero": 101,
    "serie": 1,
    "chave_acesso": "35260112345678000199550010000001011000001018",
    "status": "autorizado",
    "venda_balcao_id": 55,
    "ordem_servico_id": None,
    "cliente_id": 1,
    "cliente_nome": "Gráfica Central Ltda",
    "valor_nota": "312.50",
    "xml_path": "notas/101.xml",
    "danfe_path": "notas/101.pdf",
    "protocolo": "135260000123456",
    "mensagem_retorno": "Autorizado o uso da NF-e",
    "contingencia": False,
    "tentativas": 0,
    "created_at": "2026-02-01T09:12:00",
    "updated_at": "2026-02-01T09:12:00",
}
DOC_REJEITADO = {
    **DOC_AUTORIZADO,
    "id": 2,
    "modelo": "nfce",
    "numero": 202,
    "status": "rejeitado",
    "mensagem_retorno": "Rejeição 539: duplicidade",
    "venda_balcao_id": None,
    "ordem_servico_id": 1044,
}
DOC_CONTINGENCIA = {
    **DOC_AUTORIZADO,
    "id": 3,
    "numero": 303,
    "status": "autorizado",
    "contingencia": True,
    "mensagem_retorno": "Emitido em contingência (gateway indisponível)",
}

ESTADO: dict = {}


def _reset() -> None:
    ESTADO.clear()
    ESTADO.update(
        {
            "docs": [DOC_AUTORIZADO, DOC_REJEITADO, DOC_CONTINGENCIA],
            "resumo": {
                "total": 3,
                "por_status": {"autorizado": 2, "rejeitado": 1},
                "por_modelo": {"nfe": 2, "nfce": 1},
                "pendentes": 2,
                "em_contingencia": 1,
                "gateway_configurado": False,
                "gateway_disponivel": False,
                "mensagem": "Gateway fiscal não configurado — a emissão de NF-e/NFC-e está indisponível.",
            },
        }
    )


def _paginado(linhas: list[dict]) -> httpx.Response:
    return httpx.Response(
        200, json={"data": linhas, "meta": {"total": len(linhas), "limit": 50, "offset": 0}}
    )


def _item(dado) -> httpx.Response:
    return httpx.Response(200, json={"data": dado})


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/fiscal/documentos":
        return _paginado(ESTADO["docs"])
    if path == "/v1/fiscal/resumo":
        return _item(ESTADO["resumo"])
    if path.startswith("/v1/fiscal/documentos/"):
        item_id = int(path.rsplit("/", 1)[-1])
        doc = next((d for d in ESTADO["docs"] if d["id"] == item_id), None)
        return _item(doc)
    return httpx.Response(404, json={"detail": f"rota não esperada: {path}"})


def _api() -> Api:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "x", "login": "x"}})
    return api


@pytest.fixture(autouse=True)
def _estado_limpo():
    _reset()
    yield


@pytest.fixture(autouse=True)
def _sem_modais(monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)


# --------------------------------------------------------------------- host
def test_host_fiscal_tem_documentos_e_contingencia(app):
    pagina = PaginaFiscal(_api(), nivel="caixa")
    assert [b.text() for b in pagina._botoes] == ["Documentos Fiscais", "Contingência"]


def test_criar_pagina_mapeia_fiscal_e_ids(app):
    from printgest.ui.modulos import criar_pagina

    api = _api()
    assert isinstance(criar_pagina("fiscal", "Fiscal", api, False, "admin"), PaginaFiscal)
    assert isinstance(
        criar_pagina("documentos_fiscais", "Documentos Fiscais", api, False, "caixa"),
        PaginaDocumentosFiscais,
    )
    assert isinstance(
        criar_pagina("contingencia", "Contingência", api, False, "caixa"),
        PaginaContingencia,
    )


# -------------------------------------------------------- documentos fiscais
def test_documentos_lista_e_formata(app, pumpar):
    pagina = PaginaDocumentosFiscais(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 3)

    assert pagina._tabela.item(0, 1).text() == "NF-e"  # modelo
    assert pagina._tabela.item(0, 4).text() == "AUTORIZADO"  # status
    assert pagina._tabela.item(0, 5).text() == "R$ 312,50"  # valor
    assert pagina._tabela.item(2, 7).text() == "Sim"  # contingência


def test_documentos_e_somente_leitura(app, pumpar):
    pagina = PaginaDocumentosFiscais(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 3)

    # Sem cadastro: botões de Novo/Salvar/Cancelar ocultos e campos desabilitados.
    assert pagina._btn_novo.isHidden()
    assert pagina._btn_salvar.isHidden()
    assert pagina._btn_cancelar.isHidden()
    assert not pagina._f_modelo.widget.isEnabled()
    assert not pagina._f_chave.widget.isEnabled()

    # Selecionar uma linha preenche o formulário (consulta).
    pagina._tabela.selectRow(1)
    app.processEvents()
    assert pagina._f_status.valor() == "REJEITADO"
    assert "O.S. #1044" == pagina._f_vinculo.valor()


def test_documentos_modo_leitura_badge(app, pumpar):
    pagina = PaginaDocumentosFiscais(_api(), modo_leitura=True)
    pumpar(lambda: pagina._tabela.rowCount() == 3)
    assert not pagina._f_chave.widget.isEnabled()


# ------------------------------------------------------------- contingência
def test_contingencia_avisa_gateway_e_lista_pendencias(app, pumpar):
    pagina = PaginaContingencia(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 2)

    assert pagina._badge_gateway.text() == "GATEWAY INDISPONÍVEL"
    assert "Pendências: 2" == pagina._badge_pendentes.text()
    assert "gateway fiscal" in pagina._mensagem.text().lower()
    # Só o rejeitado e o documento marcado em contingência entram na lista.
    ids = {pagina._tabela.item(r, 0).text() for r in range(pagina._tabela.rowCount())}
    assert ids == {"#00002", "#00003"}
