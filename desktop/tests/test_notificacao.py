"""A1/A2 — rótulo de 423 e mascaramento de mensagens na UI."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from printgest.core.api import Api, ApiError
from printgest.core.notificacao import mensagem_segura, titulo_erro
from printgest.ui.modulos.pagina_crud import PaginaCrud

LOCKED = (
    "Usuário temporariamente bloqueado por excesso de tentativas. "
    "Tente novamente em 3 min."
)
LICENSE = "Sistema em modo de leitura: a licença está vencida, revogada ou ainda não foi ativada."


@pytest.mark.parametrize(
    "status,msg,esperado",
    [
        (423, LOCKED, "Usuário bloqueado"),
        (423, LICENSE, "Modo leitura"),
        (401, LOCKED, "Sessão encerrada"),
        (409, LOCKED, "Padrão"),
        (None, LOCKED, "Padrão"),
    ],
)
def test_titulo_erro(status, msg, esperado):
    assert titulo_erro(status, msg, "Padrão") == esperado


def test_mensagem_segura_mascara_segredos():
    texto = mensagem_segura("Bearer supersecreto token=abc123 senha=xyz")
    assert "supersecreto" not in texto
    assert "abc123" not in texto
    assert "xyz" not in texto
    assert "Bearer" in texto


def test_api_mascara_detalhe_e_guarda_ultimo_erro():
    def handler(_request):
        return httpx.Response(400, json={"detail": "Bearer supersecreto123"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    with pytest.raises(ApiError) as exc:
        api.listar("produtos")

    assert "supersecreto123" not in str(exc.value)
    assert "Bearer ***" in str(exc.value)
    assert "supersecreto123" not in api.ultimo_erro
    assert api.ultimo_status == 400


def test_pagina_crud_rotula_423_corretamente(monkeypatch):
    vistos: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "printgest.ui.modulos.pagina_crud.QMessageBox.warning",
        lambda _pai, titulo, texto: vistos.append((titulo, texto)),
    )
    botao = SimpleNamespace(setEnabled=lambda _valor: None)
    pagina = SimpleNamespace(_btn_salvar=botao)

    PaginaCrud._erro_salvar(pagina, LOCKED, 423)
    PaginaCrud._erro_salvar(pagina, LICENSE, 423)
    PaginaCrud._erro_salvar(pagina, "Bearer supersecreto bloqueado", 423)

    assert [titulo for titulo, _ in vistos] == [
        "Usuário bloqueado", "Modo leitura", "Usuário bloqueado"
    ]
    assert all("supersecreto" not in texto for _, texto in vistos)
