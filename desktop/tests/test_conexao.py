"""Tela 1.3 — Conectar ao Servidor (modo Estação, D6/P5).

Cobre com `httpx.MockTransport` (sem rede): normalização do endereço, teste de
conexão, Conectar persistindo o endereço e emitindo `conectado`, erro em linha
quando o servidor não responde e a confirmação de saída.
"""

from __future__ import annotations

import httpx
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

from printgest.core.api import base_url_padrao, modo_estacao
from printgest.ui.conexao import ConexaoWindow, normalizar_endereco


def _handler_caminhos(caminhos: list):
    """Handler que responde 200 para /health nos `caminhos`, 404 no resto."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in caminhos:
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"detail": "x"})

    return handler


def _janela(monkeypatch, ajustes: QSettings, handler) -> ConexaoWindow:
    monkeypatch.setattr(
        "printgest.ui.conexao.Api",
        lambda base_url: _ApiFake(base_url, handler),
    )
    return ConexaoWindow(ajustes=ajustes)


class _ApiFake:
    """Api de teste: mesmo construtor usado pela tela, com transporte mock."""

    def __init__(self, base_url: str, handler) -> None:
        import printgest.core.api as mod_api

        self._base_url = base_url
        self._handler = handler
        self._real = mod_api.Api(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    def testar_comunicacao(self) -> bool:
        return self._real.testar_comunicacao()

    def fechar(self) -> None:
        self._real.fechar()


# --------------------------------------------------------- normalização (D3)


def test_normalizar_endereco():
    assert normalizar_endereco("192.168.0.10:8000") == "http://192.168.0.10:8000"
    assert normalizar_endereco("  http://10.0.0.5:8000/ ") == "http://10.0.0.5:8000"
    assert normalizar_endereco("") == ""
    assert normalizar_endereco("servidor.local") == "http://servidor.local"


# --------------------------------------------------------- modo estação env


def test_modo_estacao_por_variaveis(monkeypatch):
    monkeypatch.delenv("PRINTGEST_API_URL", raising=False)
    monkeypatch.delenv("PRINTGEST_MODO_ESTACAO", raising=False)
    assert modo_estacao() is False
    assert base_url_padrao() == "http://127.0.0.1:8000"

    monkeypatch.setenv("PRINTGEST_API_URL", "192.168.0.10:8000")
    assert modo_estacao() is True
    assert base_url_padrao() == "http://192.168.0.10:8000"

    monkeypatch.delenv("PRINTGEST_API_URL", raising=False)
    monkeypatch.setenv("PRINTGEST_MODO_ESTACAO", "sim")
    assert modo_estacao() is True


# ------------------------------------------------------------- tela de conexão


def test_conectar_emite_endereco_normalizado_e_persiste(app, pumpar, monkeypatch, tmp_path):
    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    janela = _janela(monkeypatch, ajustes, _handler_caminhos(["/health"]))
    janela._campo.setText(" 192.168.0.10:8000/ ")
    emitidos: list[str] = []
    janela.conectado.connect(emitidos.append)

    janela._conectar()

    pumpar(lambda: len(emitidos) == 1)
    assert emitidos == ["http://192.168.0.10:8000"]
    ajustes.sync()
    assert ajustes.value("servidor/endereco") == "http://192.168.0.10:8000"


def test_endereco_salvo_prefere_o_ultimo_usado(app, monkeypatch, tmp_path):
    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    ajustes.setValue("servidor/endereco", "http://10.0.0.9:8000")
    janela = _janela(monkeypatch, ajustes, _handler_caminhos(["/health"]))
    assert janela._campo.text() == "http://10.0.0.9:8000"


def test_sem_resposta_mostra_erro_e_nao_emite(app, pumpar, monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fora do ar")

    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    janela = _janela(monkeypatch, ajustes, handler)
    emitidos: list[str] = []
    janela.conectado.connect(emitidos.append)

    janela._conectar()
    pumpar(lambda: "Não foi possível conectar" in janela._erro.text())

    assert emitidos == []
    assert janela._botao_conectar.isEnabled()
    assert "sem resposta" in janela._status.text()


def test_endereco_vazio_pede_o_campo(app, monkeypatch, tmp_path):
    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    janela = _janela(monkeypatch, ajustes, _handler_caminhos(["/health"]))
    janela._campo.setText("   ")
    janela._conectar()
    assert "Informe o endereço" in janela._erro_campo.text()


def test_botoes_tem_rotulo_altura_e_nome(app, monkeypatch, tmp_path):
    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    janela = _janela(monkeypatch, ajustes, _handler_caminhos(["/health"]))
    for trecho, botao in (
        ("Conectar", janela._botao_conectar),
        ("Testar conexão", janela._botao_testar),
        ("Sair", janela._botao_sair),
    ):
        assert trecho in botao.text()
        assert botao.minimumHeight() >= 40
        assert botao.accessibleName() == botao.text()


def test_sair_com_confirmacao(app, monkeypatch, tmp_path):
    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    janela = _janela(monkeypatch, ajustes, _handler_caminhos(["/health"]))
    respostas = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: respostas.append(1) or QMessageBox.StandardButton.Yes,
    )
    emitido = []
    janela.saida.connect(lambda: emitido.append(True))
    janela._solicitar_saida()
    assert respostas == [1]
    assert emitido == [True]


def test_campo_tem_nome_acessivel(app, monkeypatch, tmp_path):
    ajustes = QSettings(str(tmp_path / "conf.ini"), QSettings.Format.IniFormat)
    janela = _janela(monkeypatch, ajustes, _handler_caminhos(["/health"]))
    assert janela._campo.accessibleName() == "Endereço do servidor"
