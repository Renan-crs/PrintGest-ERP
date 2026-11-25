"""Fase 1 — aviso de nova versão sem instalação automática."""

from __future__ import annotations

import httpx
import pytest

from printgest.core import atualizacao
from printgest.ui.tela_principal import TelaPrincipal
from printgest.ui.widgets_atualizacao import NotificacaoAtualizacao

SHA = "a" * 64
MANIFESTO = {
    "versao": "0.5.35",
    "arquivo": "PrintGest-Setup-0.5.35.exe",
    "sha256": SHA,
    "data": "2026-11-25",
    "url": "https://github.com/Renan-crs/PrintGest-ERP/releases/tag/v0.5.35",
    "notas": ["Aviso de nova versão"],
}


def _cliente(payload=None, *, status=200, corpo=None) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status)
        if corpo is not None:
            return httpx.Response(200, text=corpo)
        return httpx.Response(200, json=MANIFESTO if payload is None else payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "atual,disponivel,esperado",
    [
        ("0.5.34", "0.5.35", True),
        ("0.5.34", "0.6.0", True),
        ("1.0.0", "0.99.99", False),
        ("0.5.35", "0.5.35", False),
        ("0.5.36", "0.5.35", False),
        ("v0.5.34", "v0.5.35", True),
        ("0.5.34", "versao-invalida", False),
    ],
)
def test_comparador_de_versao(atual, disponivel, esperado):
    assert atualizacao.versao_e_maior(atual, disponivel) is esperado


def test_manifesto_valido_gera_dados_do_banner():
    with _cliente() as cliente:
        dados = atualizacao.verificar("0.5.34", cliente)
    assert dados["versao_nova"] == "0.5.35"
    assert dados["download_url"] == MANIFESTO["url"]
    assert dados["sha256"] == SHA
    assert dados["revisoes"] == ["Aviso de nova versão"]


def test_versao_igual_ou_mais_nova_nao_avisa():
    for atual in ("0.5.35", "0.5.36"):
        with _cliente() as cliente:
            assert atualizacao.verificar(atual, cliente) is None


@pytest.mark.parametrize("status", [404, 500])
def test_erro_http_nao_levanta_e_nao_avisa(status):
    with _cliente(status=status) as cliente:
        assert atualizacao.verificar("0.5.34", cliente) is None


def test_json_invalido_nao_levanta_e_nao_avisa():
    with _cliente(corpo="{json quebrado") as cliente:
        assert atualizacao.verificar("0.5.34", cliente) is None


def test_manifesto_com_url_fora_do_github_e_rejeitado():
    dados = dict(MANIFESTO)
    dados["url"] = "https://site-estranho.example/download.exe"
    with _cliente(dados) as cliente:
        assert atualizacao.verificar("0.5.34", cliente) is None


def test_manifesto_sem_sha256_e_rejeitado():
    dados = dict(MANIFESTO)
    dados["sha256"] = "curto"
    with _cliente(dados) as cliente:
        assert atualizacao.verificar("0.5.34", cliente) is None


def test_banner_emite_url_do_release(app, monkeypatch):
    vistos: list[str] = []
    banner = NotificacaoAtualizacao(
        {
            "versao_nova": "0.5.35",
            "data": "2026-11-25",
            "revisoes": ["Melhoria"],
            "download_url": MANIFESTO["url"],
        }
    )
    banner.atualizar_solicitado.connect(vistos.append)
    banner._btn_atualizar.click()
    assert vistos == [MANIFESTO["url"]]

    monkeypatch.setattr(
        "printgest.ui.tela_principal.QDesktopServices.openUrl",
        lambda url: vistos.append(str(url.toString())),
    )
    TelaPrincipal._abrir_release(MANIFESTO["url"])
    assert MANIFESTO["url"] in vistos


def test_api_delega_para_o_manifesto(monkeypatch):
    from printgest.core.api import Api

    chamadas: list[str] = []
    esperado = {"versao_nova": "0.5.35", "download_url": MANIFESTO["url"]}
    monkeypatch.setattr(
        "printgest.core.atualizacao.verificar",
        lambda versao: chamadas.append(versao) or esperado,
    )
    api = Api(base_url="http://daemon.test")
    resultado = api.verificar_atualizacao("0.5.34")
    assert chamadas == ["0.5.34"]
    assert resultado == esperado


def test_mostrar_atualizacao_sem_dados_nao_cria_banner(app):
    tela = TelaPrincipal(api=object(), usuario={"id": 1, "nome": "Ana", "login": "ana"})
    tela._mostrar_atualizacao(None)
    assert tela._banner_atualizacao is None
