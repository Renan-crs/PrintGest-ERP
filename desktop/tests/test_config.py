"""Testes do módulo Configuração: host de abas, Dados da Empresa, Personalização,
Reajuste de Preços em Bloco (prévia + senha) e Usuários/Níveis.

O backend real é coberto por `backend/tests/test_config.py`; aqui um
`MockTransport` emula `/v1/config/*`, `/v1/categorias` e `/v1/usuarios` para
exercitar a UI sem servidor.
"""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from printgest.core.api import Api
from printgest.ui.modulos.configuracao import (
    PaginaConfiguracoes,
    PaginaEmpresa,
    PaginaPersonalizacao,
    PaginaReajuste,
    PaginaUsuarios,
)

EMPRESA = {
    "id": 1,
    "razao_social": "Printgest Gráfica LTDA",
    "nome_fantasia": "Printgest",
    "cnpj": "12345678000199",
    "inscricao_estadual": "123456",
    "inscricao_municipal": None,
    "regime_tributario": "Simples Nacional",
    "ambiente_fiscal": "h",
    "cnae_fiscal": "1813001",
    "logradouro": "Rua das Artes",
    "numero": "100",
    "complemento": None,
    "bairro": "Centro",
    "cidade": "São Paulo",
    "uf": "SP",
    "cep": "01001000",
    "telefone": "1130000000",
    "email": "contato@printgest.com",
    "website": None,
    "logotipo_path": None,
    "fundo_tela_path": None,
    "impressora_matricial": None,
    "impressora_cupom": None,
    "certificado_path": None,
    "ativa": True,
}

ESTADO: dict = {}


def _reset() -> None:
    ESTADO.clear()
    ESTADO.update(
        {
            "empresa": dict(EMPRESA),
            "empresa_gets": 0,
            "payloads": [],
            "ultimo_simular": None,
            "ultimo_aplicar": None,
            "historico": [
                {
                    "id": 7,
                    "usuario_id": 1,
                    "tipo_reajuste": "percentual",
                    "valor_reajuste": "10.0000",
                    "criterio": "categoria:3",
                    "itens_afetados": 4,
                    "executado_em": "2026-02-01T10:00:00",
                }
            ],
            "categorias": [
                {"id": 3, "nome": "Impressão", "ativo": True},
                {"id": 4, "nome": "Acabamento", "ativo": True},
            ],
            "previa": {
                "total": 3,
                "afetados": 2,
                "bloqueados": 1,
                "itens": [
                    {
                        "produto_id": 11,
                        "codigo": "P1",
                        "nome": "Banner",
                        "preco_antes": "100.00",
                        "preco_depois": "110.00",
                    },
                    {
                        "produto_id": 12,
                        "codigo": "P2",
                        "nome": "Cartão",
                        "preco_antes": "50.00",
                        "preco_depois": "55.00",
                    },
                ],
            },
            "usuarios": [
                {
                    "id": 1,
                    "nome": "Ana Admin",
                    "login": "ana",
                    "email": "ana@pg.com",
                    "nivel_acesso": "admin",
                    "ativo": True,
                },
                {
                    "id": 2,
                    "nome": "Caio Caixa",
                    "login": "caio",
                    "email": None,
                    "nivel_acesso": "caixa",
                    "ativo": False,
                },
            ],
        }
    )


def _paginado(linhas: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": linhas, "meta": {"total": len(linhas), "limit": 50, "offset": 0}},
    )


def _item(dado) -> httpx.Response:
    return httpx.Response(200, json={"data": dado})


def _corpo(request: httpx.Request) -> dict:
    return json.loads(request.content or b"{}")


def _handler(request: httpx.Request) -> httpx.Response:
    path, metodo = request.url.path, request.method

    if path == "/v1/config/empresa":
        if metodo == "GET":
            ESTADO["empresa_gets"] += 1
            return _item(ESTADO["empresa"])
        payload = _corpo(request)
        ESTADO["payloads"].append(payload)
        for chave, valor in payload.items():
            if valor is None and chave in ("razao_social", "cnpj", "ambiente_fiscal", "ativa"):
                continue  # coluna NOT NULL não é apagada
            ESTADO["empresa"][chave] = valor
        return _item(ESTADO["empresa"])

    if path == "/v1/config/reajuste/simular":
        ESTADO["ultimo_simular"] = _corpo(request)
        return _item(ESTADO["previa"])

    if path == "/v1/config/reajuste/aplicar":
        payload = _corpo(request)
        ESTADO["ultimo_aplicar"] = payload
        ESTADO["historico"].insert(
            0,
            {
                "id": 8,
                "usuario_id": 1,
                "tipo_reajuste": payload.get("tipo_reajuste"),
                "valor_reajuste": payload.get("valor"),
                "criterio": f"categoria:{payload.get('categoria_id')}",
                "itens_afetados": ESTADO["previa"]["afetados"],
                "executado_em": "2026-02-02T12:00:00",
            },
        )
        return _item(
            {
                "historico_id": 8,
                "afetados": ESTADO["previa"]["afetados"],
                "executado_em": "2026-02-02T12:00:00",
            }
        )

    if path == "/v1/config/reajuste/historico":
        return _paginado(ESTADO["historico"])

    if path == "/v1/categorias":
        return _paginado(ESTADO["categorias"])

    if path == "/v1/usuarios":
        if metodo == "GET":
            return _paginado(ESTADO["usuarios"])
        payload = _corpo(request)
        ESTADO["payloads"].append(payload)
        novo = {
            "id": 99,
            "nome": payload.get("nome"),
            "login": payload.get("login"),
            "email": payload.get("email"),
            "nivel_acesso": payload.get("nivel_acesso"),
            "ativo": payload.get("ativo", True),
        }
        ESTADO["usuarios"].insert(0, novo)
        return _item(novo)

    if path.startswith("/v1/usuarios/"):
        item_id = int(path.rsplit("/", 1)[-1])
        payload = _corpo(request)
        ESTADO["payloads"].append(payload)
        alvo = next(u for u in ESTADO["usuarios"] if u["id"] == item_id)
        alvo.update({k: v for k, v in payload.items() if k != "senha"})
        return _item(alvo)

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
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok
    )


# ------------------------------------------------------------------------- host
def test_host_configuracoes_admin_tem_quatro_abas(app):
    pagina = PaginaConfiguracoes(_api(), nivel="admin")
    assert [b.text() for b in pagina._botoes] == [
        "Dados da Empresa",
        "Personalização",
        "Reajuste de Preços",
        "Usuários e Níveis",
    ]


def test_host_configuracoes_restrito_para_nao_admin(app):
    pagina = PaginaConfiguracoes(_api(), nivel="gerente")
    assert pagina._abas == []
    assert pagina._botoes == []


def test_criar_pagina_mapeia_configuracao_e_ids_internos(app):
    from printgest.ui.modulos import criar_pagina

    api = _api()
    assert isinstance(
        criar_pagina("configuracoes", "Configurações", api, False, "admin"),
        PaginaConfiguracoes,
    )
    assert isinstance(
        criar_pagina("dados_empresa", "Dados da Empresa", api, False, "admin"),
        PaginaEmpresa,
    )
    assert isinstance(
        criar_pagina("personalizacao", "Personalização", api, False, "admin"),
        PaginaPersonalizacao,
    )
    assert isinstance(
        criar_pagina("reajuste_bloco", "Reajuste", api, False, "admin"),
        PaginaReajuste,
    )
    assert isinstance(
        criar_pagina("usuarios", "Usuários", api, False, "admin"), PaginaUsuarios
    )


# ------------------------------------------------------------- dados da empresa
def test_empresa_carrega_e_salva(app, pumpar):
    pagina = PaginaEmpresa(_api())
    pumpar(lambda: pagina._razao.valor() == "Printgest Gráfica LTDA")
    assert pagina._cidade.valor() == "São Paulo"
    assert pagina._ambiente.valor() == "h"

    pagina._fantasia.definir("Printgest Novo")
    pagina._salvar()
    pumpar(lambda: pagina._status.text() == "Alterações salvas.")

    assert ESTADO["empresa"]["nome_fantasia"] == "Printgest Novo"
    # O PUT envia o cadastro completo (não só o campo alterado).
    assert "razao_social" in ESTADO["payloads"][-1]
    assert "logradouro" in ESTADO["payloads"][-1]


def test_empresa_exige_razao_social(app, pumpar):
    pagina = PaginaEmpresa(_api())
    pumpar(lambda: pagina._razao.valor() != "")
    pagina._razao.definir("")
    pagina._salvar()
    app.processEvents()
    assert ESTADO["payloads"] == []  # bloqueado na validação


def test_empresa_modo_leitura_bloqueia(app, pumpar):
    pagina = PaginaEmpresa(_api(), modo_leitura=True)
    pumpar(lambda: pagina._razao.valor() != "")
    assert not pagina._btn_salvar.isEnabled()
    assert not pagina._razao.widget.isEnabled()


# --------------------------------------------------------------- personalização
def test_personalizacao_envia_somente_suas_chaves(app, pumpar):
    pagina = PaginaPersonalizacao(_api())
    # Espera o carregamento concluir (status sai de "Carregando…" para ""),
    # senão o `_preencher` de resposta tardia apagaria o que acabamos de digitar.
    pumpar(lambda: pagina._status.text() == "")

    pagina._logotipo.definir("C:/pg/logo.png")
    pagina._matricial.definir("EPSON LX-300")
    pagina._salvar()
    pumpar(lambda: pagina._status.text() == "Alterações salvas.")

    assert set(ESTADO["payloads"][-1].keys()) == {
        "logotipo_path",
        "fundo_tela_path",
        "impressora_matricial",
        "impressora_cupom",
    }
    assert ESTADO["empresa"]["logotipo_path"] == "C:/pg/logo.png"
    # Atualização parcial preserva o restante do cadastro.
    assert ESTADO["empresa"]["razao_social"] == "Printgest Gráfica LTDA"


# ------------------------------------------------------------------- reajuste
def test_reajuste_simula_e_aplica_com_senha(app, pumpar, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("admin123", True))
    pagina = PaginaReajuste(_api())
    pumpar(lambda: pagina._categoria.widget.count() == 2)

    pagina._criterio.definir("categoria")
    pagina._categoria.definir(3)
    pagina._tipo.definir("percentual")
    pagina._valor.definir("10")
    pagina._simular()
    pumpar(lambda: pagina._tabela.rowCount() == 2)

    assert "2 produto(s)" in pagina._resumo.text()
    assert "1 bloqueado" in pagina._resumo.text()
    assert pagina._tabela.item(0, 2).text() == "R$ 100,00"
    assert pagina._tabela.item(0, 3).text() == "R$ 110,00"
    assert pagina._tabela.item(0, 4).text() == "+10,0%"
    assert pagina._btn_aplicar.isEnabled()
    assert ESTADO["ultimo_simular"]["categoria_id"] == 3
    assert ESTADO["ultimo_simular"]["tipo_reajuste"] == "percentual"

    pagina._aplicar()
    pumpar(lambda: pagina._previa is None)

    assert ESTADO["ultimo_aplicar"]["senha"] == "admin123"
    assert pagina._tabela.rowCount() == 0


def test_reajuste_simular_exige_valor(app, pumpar):
    pagina = PaginaReajuste(_api())
    pumpar(lambda: pagina._categoria.widget.count() == 2)
    pagina._simular()
    app.processEvents()
    assert ESTADO["ultimo_simular"] is None  # bloqueado antes de chamar a API


def test_reajuste_modo_leitura_bloqueia(app, pumpar):
    pagina = PaginaReajuste(_api(), modo_leitura=True)
    pumpar(lambda: pagina._categoria.widget.count() == 2)
    assert not pagina._btn_simular.isEnabled()
    assert not pagina._btn_aplicar.isEnabled()
    assert not pagina._valor.widget.isEnabled()


def test_reajuste_historico_mostra_trilha(app, pumpar):
    pagina = PaginaReajuste(_api())
    pumpar(lambda: "10%" in pagina._historico.text())
    assert "categoria:3" in pagina._historico.text()


# ------------------------------------------------------------------- usuários
def test_usuarios_lista_e_formata(app, pumpar):
    pagina = PaginaUsuarios(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 2)

    assert pagina._tabela.item(0, 0).text() == "#00001"
    assert pagina._tabela.item(0, 3).text() == "Administrador"
    assert pagina._tabela.item(1, 5).text() == "Não"

    pagina._tabela.selectRow(1)
    app.processEvents()
    assert pagina._nome.valor() == "Caio Caixa"
    assert not pagina._login.widget.isEnabled()  # login é imutável na edição


def test_usuarios_cria_com_login_e_senha(app, pumpar):
    pagina = PaginaUsuarios(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 2)

    pagina._novo()
    app.processEvents()
    assert pagina._login.widget.isEnabled()

    pagina._nome.definir("Novo Operador")
    pagina._login.definir("novo.op")
    pagina._nivel.definir("operador")
    pagina._senha.definir("senha12345")
    pagina._salvar()
    pumpar(lambda: len(ESTADO["usuarios"]) == 3)

    payload = ESTADO["payloads"][-1]
    assert payload["login"] == "novo.op"
    assert payload["senha"] == "senha12345"
    assert payload["nivel_acesso"] == "operador"
