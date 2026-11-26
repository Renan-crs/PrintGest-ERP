"""Fase 2 — download validado e disparo destacado do instalador."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from printgest.core import instalador_atualizacao as ia
from printgest.core.instalador_atualizacao import ErroAtualizacao

CONTEUDO = b"setup-falso"
SHA = hashlib.sha256(CONTEUDO).hexdigest()
INFO = {
    "arquivo": "PrintGest-Setup-0.5.36.exe",
    "sha256": SHA,
    "download_url": "https://github.com/Renan-crs/PrintGest-ERP/releases/download/v0.5.36/PrintGest-Setup-0.5.36.exe",
    "versao_nova": "0.5.36",
}


def _cliente(conteudo=CONTEUDO, *, status=200) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, content=conteudo)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


@pytest.fixture(autouse=True)
def _pasta_temporaria(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    yield tmp_path


def test_baixa_e_valida_sha256():
    with _cliente() as cliente:
        caminho = ia.baixar_instalador(INFO, cliente)
    assert caminho.name == INFO["arquivo"]
    assert caminho.read_bytes() == CONTEUDO
    assert not caminho.with_suffix(".download").exists()


def test_hash_divergente_nao_entrega_nem_executa():
    dados = dict(INFO, sha256="0" * 64)
    with _cliente() as cliente, pytest.raises(ErroAtualizacao, match="SHA-256"):
        ia.baixar_instalador(dados, cliente)
    assert not list(ia.diretorio_downloads().glob("*.exe"))
    assert not list(ia.diretorio_downloads().glob("*.download"))


def test_arquivo_ja_validado_e_reaproveitado():
    destino = ia.diretorio_downloads() / INFO["arquivo"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(CONTEUDO)

    def nao_deve_baixar(_request):
        raise AssertionError("Não deveria fazer GET")

    cliente = httpx.Client(transport=httpx.MockTransport(nao_deve_baixar))
    with cliente:
        assert ia.baixar_instalador(INFO, cliente) == destino


def test_url_fora_do_github_e_rejeitada():
    dados = dict(INFO, download_url="https://estranho.example/setup.exe")
    with pytest.raises(ErroAtualizacao, match="GitHub"):
        ia.baixar_instalador(dados, _cliente())


def test_http_500_levanta_erro_amigavel():
    with _cliente(status=500) as cliente, pytest.raises(ErroAtualizacao, match="HTTP 500"):
        ia.baixar_instalador(INFO, cliente)


def test_iniciar_instalador_em_processo_destacado(monkeypatch):
    chamados: dict = {}

    class FalsoProcesso:
        pid = 4242

    def falso_popen(args, **kwargs):
        chamados["args"] = args
        chamados["kwargs"] = kwargs
        return FalsoProcesso()

    monkeypatch.setattr(ia.subprocess, "Popen", falso_popen)
    caminho = ia.diretorio_downloads() / INFO["arquivo"]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(CONTEUDO)

    assert ia.iniciar_instalador(caminho) == 4242
    assert chamados["args"] == [str(caminho), "/VERYSILENT", "/NORESTART"]
    flags = chamados["kwargs"]["creationflags"]
    assert flags & getattr(ia.subprocess, "DETACHED_PROCESS", 1)
    assert chamados["kwargs"]["close_fds"] is True


def test_iniciar_instalador_inexistente():
    with pytest.raises(ErroAtualizacao, match="não encontrado"):
        ia.iniciar_instalador(Path("nao-existe.exe"))


def test_banner_emite_sinal_de_instalacao(app):
    from printgest.ui.widgets_atualizacao import NotificacaoAtualizacao

    vistos: list[dict] = []
    banner = NotificacaoAtualizacao({"versao_nova": "0.5.36", "download_url": INFO["download_url"]})
    banner.instalacao_solicitada.connect(vistos.append)
    banner._btn_instalar.click()
    assert vistos[0]["versao_nova"] == "0.5.36"


def test_gate_de_perfil_para_instalar(app, monkeypatch):
    from printgest.ui.tela_principal import TelaPrincipal
    import printgest.ui.tela_principal as modulo

    monkeypatch.setattr(modulo, "modo_estacao", lambda: False)
    operador = TelaPrincipal(api=object(), usuario={"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "operador"})
    assert operador._pode_instalar_atualizacao() is False

    gerente = TelaPrincipal(api=object(), usuario={"id": 2, "nome": "Gestor", "login": "gestor", "nivel_acesso": "gerente"})
    assert gerente._pode_instalar_atualizacao() is True

    monkeypatch.setattr(modulo, "modo_estacao", lambda: True)
    assert operador._pode_instalar_atualizacao() is True


def test_confirmacao_explica_atualizacao_em_modo_leitura(app, monkeypatch, tmp_path):
    from printgest.ui.tela_principal import TelaPrincipal
    import printgest.ui.tela_principal as modulo

    monkeypatch.setattr(modulo, "modo_estacao", lambda: False)
    tela = TelaPrincipal(
        api=object(),
        usuario={"id": 1, "nome": "Admin", "login": "admin", "nivel_acesso": "admin"},
        modo_leitura=True,
    )
    vistos: list[str] = []
    monkeypatch.setattr(
        modulo.QMessageBox,
        "question",
        lambda _pai, _titulo, texto, *_a, **_k: vistos.append(texto)
        or modulo.QMessageBox.StandardButton.No,
    )
    tela._instalar_atualizacao(dict(INFO))
    assert vistos
    assert "modo leitura" in vistos[0].lower()
    assert "regularizar" in vistos[0].lower()


def test_fluxo_completo_de_instalacao(app, monkeypatch, tmp_path):
    """Confirma → baixa → valida → dispara, sem tocar no processo real."""
    from printgest.ui.tela_principal import TelaPrincipal
    import printgest.ui.tela_principal as modulo

    monkeypatch.setattr(modulo, "modo_estacao", lambda: False)
    tela = TelaPrincipal(api=object(), usuario={"id": 1, "nome": "Admin", "login": "admin", "nivel_acesso": "admin"})
    monkeypatch.setattr(
        modulo.QMessageBox, "question", lambda *_a, **_k: modulo.QMessageBox.StandardButton.Yes
    )
    monkeypatch.setattr(modulo.QMessageBox, "information", lambda *_a, **_k: None)
    monkeypatch.setattr(
        modulo, "rodar", lambda fn, on_ok, on_erro: on_ok(fn())
    )
    monkeypatch.setattr(
        "printgest.core.instalador_atualizacao.baixar_instalador",
        lambda info: tmp_path / "setup.exe",
    )
    iniciados: list[Path] = []
    monkeypatch.setattr(
        "printgest.core.instalador_atualizacao.iniciar_instalador",
        lambda caminho: iniciados.append(caminho),
    )

    tela._instalar_atualizacao(dict(INFO))
    assert iniciados == [tmp_path / "setup.exe"]
