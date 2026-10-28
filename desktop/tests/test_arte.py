"""Testes da UI de arte, prova e aprovação (M3, PRD v3.0 §3.5).

Cobre o `DialogoArte` (estado derivado, versões, upload multipart,
decisão aprovada/ajuste com comentário obrigatório, link de prova) e o
botão "Arte (F11)" da página de O.S.
"""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from printgest.core.api import Api
from printgest.ui.modulos.os import DialogoArte, PaginaOS

# ------------------------------------------------------------- estado do mock

_V1 = {
    "id": 1, "os_id": 7, "versao": 1, "nome_arquivo": "flyer.png",
    "hash_sha256": "a" * 64, "tamanho_bytes": 2048,
    "criado_em": "2026-10-27T10:00:00",
}
_V2 = {
    "id": 2, "os_id": 7, "versao": 2, "nome_arquivo": "flyer_v2.png",
    "hash_sha256": "b" * 64, "tamanho_bytes": 4096,
    "criado_em": "2026-10-27T15:30:00",
}

# estado mutável: as ações do diálogo mudam o que o servidor devolve
_estado: dict = {}


def _reset(versoes: list[dict] | None = None, estado: str = "aguardando_aprovacao"):
    _estado.clear()
    _estado.update({
        "versoes": list(versoes if versoes is not None else [_V2, _V1]),
        "estado": estado,
        "uploads": [],      # corpos multipart recebidos
        "decisoes": [],     # (versao_id, corpo_json)
        "links": 0,
    })


def _handler(request: httpx.Request) -> httpx.Response:
    p = request.url.path
    if p == "/v1/os/7/arte" and request.method == "GET":
        return httpx.Response(
            200, json={"data": _estado["versoes"], "estado": _estado["estado"]}
        )
    if p == "/v1/os/7/arte" and request.method == "POST":
        _estado["uploads"].append(request.read())
        nova = dict(_V1)
        nova.update({
            "id": 3, "versao": len(_estado["versoes"]) + 1,
            "nome_arquivo": "nova.png", "tamanho_bytes": 100,
            "criado_em": "2026-10-28T09:00:00",
        })
        _estado["versoes"].insert(0, nova)
        _estado["estado"] = "aguardando_aprovacao"
        return httpx.Response(201, json={"data": nova})
    if p.startswith("/v1/os/7/arte/") and p.endswith("/decisao"):
        import json as _json

        corpo = _json.loads(request.read())
        partes = p.split("/")
        versao_id = int(partes[5])
        _estado["decisoes"].append((versao_id, corpo))
        _estado["estado"] = (
            "aprovada" if corpo["decisao"] == "aprovada" else "ajuste_solicitado"
        )
        return httpx.Response(201, json={"data": {"id": 9, **corpo}})
    if p == "/v1/os/7/arte/link" and request.method == "POST":
        _estado["links"] += 1
        return httpx.Response(
            200,
            json={"data": {"token": "tok-abc123-xyz", "tipo": "prova",
                           "expira_em": "2026-10-31T09:00:00"}},
        )
    # rotas da PaginaOS
    if p == "/v1/os" and request.method == "GET":
        return httpx.Response(
            200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
        )
    if p in ("/v1/clientes", "/v1/funcionarios", "/v1/produtos", "/v1/fornecedores"):
        return httpx.Response(
            200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}}
        )
    return httpx.Response(200, json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}})


def _api():
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({
        "token": "t",
        "usuario": {"id": 1, "nome": "Admin", "login": "admin", "nivel_acesso": "admin"},
    })
    return api


@pytest.fixture
def avisos(monkeypatch):
    """Captura QMessageBox (modal trava o loop offscreen)."""
    capturados: list[tuple[str, str]] = []

    def _registrar(tipo):
        def _fn(_pai, _titulo, texto, *_a, **_k):
            capturados.append((tipo, texto))
            return QMessageBox.StandardButton.Ok

        return staticmethod(_fn)

    for tipo in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, tipo, _registrar(tipo))
    return capturados


# ------------------------------------------------------------- estado/listagem


def test_carrega_versoes_e_estado(app, avisos):
    _reset()
    dialogo = DialogoArte(None, _api(), 7)
    assert dialogo._tabela.rowCount() == 2
    # mais recente primeiro (v2 no topo)
    assert dialogo._tabela.item(0, 0).text() == "v2"
    assert dialogo._tabela.item(0, 1).text() == "flyer_v2.png"
    assert "4 KB" in dialogo._tabela.item(0, 2).text()
    assert "27/10/2026 15:30" in dialogo._tabela.item(0, 3).text()
    # estado
    assert "Aguardando aprovação" in dialogo._lbl_estado.text()
    assert dialogo._btn_aprovar.isEnabled()
    assert dialogo._btn_ajuste.isEnabled()


def test_estado_sem_arte_desabilita_decisao(app, avisos):
    _reset(versoes=[], estado="sem_arte")
    dialogo = DialogoArte(None, _api(), 7)
    assert dialogo._tabela.rowCount() == 0
    assert "Nenhuma arte" in dialogo._lbl_estado.text()
    assert not dialogo._btn_aprovar.isEnabled()
    assert not dialogo._btn_ajuste.isEnabled()


def test_estado_aprovada_muda_role(app, avisos):
    _reset(estado="aprovada")
    dialogo = DialogoArte(None, _api(), 7)
    assert "aprovada" in dialogo._lbl_estado.text().lower()
    assert dialogo._lbl_estado.property("role") == "success"


# --------------------------------------------------------------------- upload


def test_upload_envia_multipart_e_recarrega(app, avisos, monkeypatch, tmp_path):
    _reset()
    arquivo = tmp_path / "nova_arte.png"
    arquivo.write_bytes(b"PNG fake de teste")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(arquivo), "")),
    )

    dialogo = DialogoArte(None, _api(), 7)
    assert dialogo._tabela.rowCount() == 2
    dialogo._btn_enviar.click()

    assert len(_estado["uploads"]) == 1
    corpo = _estado["uploads"][0]
    assert b"nova_arte.png" in corpo  # filename no multipart
    assert b"PNG fake de teste" in corpo  # conteúdo
    # recarregou com a v3 no topo
    assert dialogo._tabela.rowCount() == 3
    assert dialogo._tabela.item(0, 0).text() == "v3"


def test_upload_bloqueia_extensao_executavel(app, avisos, monkeypatch, tmp_path):
    _reset()
    arquivo = tmp_path / "virus.exe"
    arquivo.write_bytes(b"MZ")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(arquivo), "")),
    )

    dialogo = DialogoArte(None, _api(), 7)
    dialogo._btn_enviar.click()

    assert _estado["uploads"] == []  # nada chegou ao servidor
    assert any("não é permitida" in texto for _, texto in avisos)


def test_upload_arquivo_vazio_avisa(app, avisos, monkeypatch, tmp_path):
    _reset()
    arquivo = tmp_path / "vazio.png"
    arquivo.write_bytes(b"")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        staticmethod(lambda *a, **k: (str(arquivo), "")),
    )

    dialogo = DialogoArte(None, _api(), 7)
    dialogo._btn_enviar.click()
    assert _estado["uploads"] == []
    assert any("vazio" in texto for _, texto in avisos)


def test_upload_cancelado_nao_envia(app, avisos, monkeypatch):
    _reset()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))
    )
    dialogo = DialogoArte(None, _api(), 7)
    dialogo._btn_enviar.click()
    assert _estado["uploads"] == []


# ------------------------------------------------------------------- decisão


def test_aprovar_marcada_envia_decisao(app, avisos):
    _reset()
    dialogo = DialogoArte(None, _api(), 7)
    dialogo._tabela.selectRow(0)  # v2 (id 2)
    dialogo._btn_aprovar.click()

    assert _estado["decisoes"] == [(2, {"decisao": "aprovada"})]
    assert "aprovada" in dialogo._lbl_estado.text().lower()


def test_aprovar_sem_selecao_avisa(app, avisos):
    _reset()
    dialogo = DialogoArte(None, _api(), 7)
    dialogo._btn_aprovar.click()  # nenhuma linha marcada
    assert _estado["decisoes"] == []
    assert any("Selecione uma versão" in texto for _, texto in avisos)


def test_ajuste_envia_comentario(app, avisos, monkeypatch):
    _reset()
    monkeypatch.setattr(
        QInputDialog, "getMultiLineText",
        staticmethod(lambda *a, **k: ("Logo maior no cabeçalho", True)),
    )
    dialogo = DialogoArte(None, _api(), 7)
    dialogo._tabela.selectRow(0)
    dialogo._btn_ajuste.click()

    assert _estado["decisoes"] == [
        (2, {"decisao": "ajuste", "comentarios": "Logo maior no cabeçalho"})
    ]
    assert "ajuste" in dialogo._lbl_estado.text().lower()


def test_ajuste_sem_comentario_avisa_e_nao_envia(app, avisos, monkeypatch):
    _reset()
    monkeypatch.setattr(
        QInputDialog, "getMultiLineText", staticmethod(lambda *a, **k: ("", True))
    )
    dialogo = DialogoArte(None, _api(), 7)
    dialogo._tabela.selectRow(0)
    dialogo._btn_ajuste.click()

    assert _estado["decisoes"] == []
    assert any("Descreva o ajuste" in texto for _, texto in avisos)


# ---------------------------------------------------------------------- link


def test_link_copia_token_para_area_transferencia(app, avisos):
    _reset()
    dialogo = DialogoArte(None, _api(), 7)
    dialogo._btn_link.click()

    from PySide6.QtWidgets import QApplication

    assert _estado["links"] == 1
    assert QApplication.clipboard().text() == "tok-abc123-xyz"
    assert any("tok-abc123-xyz" in texto for _, texto in avisos)
    assert any("expira" in texto.lower() for _, texto in avisos)


# ------------------------------------------------------------------ página


def test_pagina_os_tem_botao_arte(app, avisos):
    from PySide6.QtWidgets import QLabel

    _reset()
    pagina = PaginaOS(_api())
    assert pagina._btn_arte.text() == "Arte"
    # hint de teclado F11 ao lado do botão (padrão botao_com_atalho)
    caixa = pagina._btn_arte.parentWidget()
    hints = [lbl.text() for lbl in caixa.findChildren(QLabel)]
    assert "F11" in hints


def test_pagina_sem_selecao_avisa_ao_abrir_arte(app, avisos):
    _reset()
    pagina = PaginaOS(_api())
    assert pagina._editando_id is None
    pagina._btn_arte.click()
    assert any("Selecione uma O.S." in texto for _, texto in avisos)
