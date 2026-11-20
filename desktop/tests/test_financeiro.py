"""Testes do módulo Financeiro: host de abas, Caixa (abertura/extrato/fechamento),
Contas a Receber (lista + baixa) e Plano de Contas (cadastro).

O backend real é coberto por `backend/tests/test_financeiro.py`; aqui um
`MockTransport` stateful emula caixa/contas para exercitar a UI sem servidor.
"""

from __future__ import annotations

import json

import httpx
import pytest
from PySide6.QtWidgets import QMessageBox

from printgest.core.api import Api
from printgest.ui.modulos.financeiro import (
    PaginaCaixa,
    PaginaContasReceber,
    PaginaFinanceiro,
    PaginaPlanoContas,
)

_CLIENTES = [{"id": 1, "nome_razao": "Ana"}]

ESTADO: dict = {}


def _reset() -> None:
    ESTADO.clear()
    ESTADO.update(
        {
            "caixa": None,
            "extrato": [],
            "seq": 1,
            "contas": [
                {
                    "id": 11,
                    "descricao": "Parcela 1/1 — O.S. 1044",
                    "cliente_id": 1,
                    "cliente_nome": "Ana",
                    "vencimento": "2026-02-10",
                    "valor": "100.00",
                    "valor_pago": "0.00",
                    "status": "aberta",
                    "data_pagamento": None,
                    "observacoes": None,
                }
            ],
            "plano": [],
            "baixas": [],
            "criados": [],
        }
    )


def _paginado(linhas: list[dict]) -> httpx.Response:
    return httpx.Response(
        200, json={"data": linhas, "meta": {"total": len(linhas), "limit": 50, "offset": 0}}
    )


def _item(dado) -> httpx.Response:
    return httpx.Response(200, json={"data": dado})


def _recalcular() -> None:
    abertura = float(ESTADO["caixa"]["valor_abertura"])
    entradas = sum(
        float(m["valor"])
        for m in ESTADO["extrato"]
        if m["tipo"] in ("entrada", "suprimento")
    )
    saidas = sum(
        float(m["valor"]) for m in ESTADO["extrato"] if m["tipo"] in ("saida", "sangria")
    )
    ESTADO["caixa"].update(
        {
            "total_entradas": f"{entradas:.2f}",
            "total_saidas": f"{saidas:.2f}",
            "saldo_atual": f"{abertura + entradas - saidas:.2f}",
        }
    )


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    corpo = json.loads(request.content) if request.content else {}

    if path == "/v1/financeiro/caixa/atual":
        return _item(ESTADO["caixa"])
    if path == "/v1/financeiro/caixa/abrir":
        ESTADO["caixa"] = {
            "id": 7,
            "status": "aberto",
            "valor_abertura": f"{float(corpo.get('valor_abertura') or 0):.2f}",
            "total_entradas": "0.00",
            "total_saidas": "0.00",
            "saldo_atual": f"{float(corpo.get('valor_abertura') or 0):.2f}",
        }
        return _item(ESTADO["caixa"])
    if path == "/v1/financeiro/caixa/7/extrato":
        return _paginado(ESTADO["extrato"])
    if path == "/v1/financeiro/caixa/7/movimento":
        novo = {
            "id": ESTADO["seq"],
            "tipo": corpo["tipo"],
            "descricao": corpo.get("descricao"),
            "valor": corpo["valor"],
            "criado_em": "2026-02-01T10:00:00",
        }
        ESTADO["seq"] += 1
        ESTADO["extrato"].append(novo)
        _recalcular()
        return _item(novo)
    if path == "/v1/financeiro/caixa/7/fechar":
        caixa = ESTADO["caixa"]
        esperado = float(caixa["saldo_atual"])
        # Sem valor informado o backend adota o esperado (conferência dispensada).
        informado = float(corpo.get("valor_informado") or esperado)
        caixa.update(
            {
                "status": "fechado",
                "valor_esperado": caixa["saldo_atual"],
                "valor_informado": f"{informado:.2f}",
                "diferenca": f"{informado - esperado:.2f}",
            }
        )
        ESTADO["caixa"] = None
        return _item(caixa)
    if path == "/v1/financeiro/contas-receber":
        return _paginado(ESTADO["contas"])
    if path.startswith("/v1/financeiro/contas-receber/") and path.endswith("/baixa"):
        conta_id = int(path.split("/")[-2])
        conta = next(c for c in ESTADO["contas"] if c["id"] == conta_id)
        conta["valor_pago"] = corpo.get("valor_pago") or conta["valor"]
        conta["data_pagamento"] = corpo.get("data_pagamento") or "2026-02-01"
        if float(conta["valor_pago"]) >= float(conta["valor"]):
            conta["status"] = "paga"
        ESTADO["baixas"].append((conta_id, corpo))
        return _item(conta)
    if path == "/v1/plano-contas" and request.method == "GET":
        return _paginado(ESTADO["plano"])
    if path == "/v1/plano-contas" and request.method == "POST":
        novo = {"id": len(ESTADO["plano"]) + 1, "ativo": True, **corpo}
        ESTADO["plano"].append(novo)
        ESTADO["criados"].append(corpo)
        return _item(novo)
    if path == "/v1/clientes":
        return _paginado(_CLIENTES)
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
    """Impede que os `QMessageBox` modais travem o loop de eventos no offscreen."""
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)


# --------------------------------------------------------------------- host
def test_host_mostra_abas_conforme_o_nivel(app, pumpar):
    admin = PaginaFinanceiro(_api(), nivel="admin")
    assert [b.text() for b in admin._botoes] == [
        "Caixa",
        "Contas a Receber",
        "Contas a Pagar",
        "Plano de Contas",
    ]

    caixa = PaginaFinanceiro(_api(), nivel="caixa")
    assert [b.text() for b in caixa._botoes] == ["Caixa"]


def test_criar_pagina_mapeia_modulo_e_ids_internos(app):
    from printgest.ui.modulos import criar_pagina

    api = _api()
    assert isinstance(criar_pagina("financeiro", "Financeiro", api, False, "admin"), PaginaFinanceiro)
    assert isinstance(criar_pagina("caixa", "Caixa", api, False, "caixa"), PaginaCaixa)
    assert isinstance(
        criar_pagina("contas_receber", "Contas a Receber", api, False, "gerente"),
        PaginaContasReceber,
    )
    assert isinstance(
        criar_pagina("plano_contas", "Plano de Contas", api, False, "gerente"),
        PaginaPlanoContas,
    )


# -------------------------------------------------------------------- caixa
def test_caixa_abre_lanca_movimento_e_fecha(app, pumpar):
    pagina = PaginaCaixa(_api())
    pumpar(lambda: pagina._btn_abrir.isEnabled() and not pagina._painel_abertura.isHidden())
    assert not pagina._painel_abertura.isHidden()
    assert pagina._painel_movimento.isHidden()

    pagina._f_abertura.definir("200,00")
    pagina._abrir()
    pumpar(lambda: pagina._caixa is not None)
    assert pagina._badge_status.text() == "CAIXA ABERTO"
    assert "R$ 200,00" in pagina._badge_saldo.text()

    pagina._f_tipo.definir("suprimento")
    pagina._f_valor.definir("50,00")
    pagina._lancar()
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert "+ R$ 50,00" == pagina._tabela.item(0, 3).text()

    pagina._f_informado.definir("250,00")
    pagina._fechar()
    pumpar(lambda: pagina._caixa is None and pagina._caixa_id_extrato == 7)
    assert pagina._badge_status.text() == "SEM CAIXA"
    assert ESTADO["extrato"][0]["tipo"] == "suprimento"


def test_caixa_fechado_mantem_extrato_visivel(app, pumpar):
    ESTADO["caixa"] = {
        "id": 7,
        "status": "aberto",
        "valor_abertura": "100.00",
        "total_entradas": "0.00",
        "total_saidas": "0.00",
        "saldo_atual": "100.00",
    }
    ESTADO["extrato"] = [
        {
            "id": 1,
            "tipo": "sangria",
            "descricao": "Retirada",
            "valor": "30.00",
            "criado_em": "2026-02-01T09:00:00",
        }
    ]
    pagina = PaginaCaixa(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert pagina._tabela.item(0, 1).text() == "SANGRIA"
    assert pagina._tabela.item(0, 3).text() == "- R$ 30,00"


def test_caixa_modo_leitura_bloqueia_abertura(app, pumpar):
    pagina = PaginaCaixa(_api(), modo_leitura=True)
    pumpar(lambda: not pagina._btn_abrir.isEnabled())
    assert not pagina._btn_abrir.isEnabled()
    pagina._abrir()
    assert ESTADO["caixa"] is None


# ------------------------------------------------------------------- contas
def test_contas_receber_lista_e_baixa(app, pumpar, monkeypatch):
    import printgest.ui.modulos.financeiro as financeiro

    monkeypatch.setattr(
        financeiro,
        "_dialogo_baixa",
        lambda *a, **k: {
            "valor_pago": "100.00",
            "data_pagamento": "2026-02-01",
            "observacoes": None,
        },
    )
    pagina = PaginaContasReceber(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 1)

    pagina._tabela.selectRow(0)
    pagina._dar_baixa()
    pumpar(lambda: ESTADO["contas"][0]["status"] == "paga")

    assert ESTADO["baixas"][0][0] == 11
    assert pagina._acoes_extra  # a ação de baixa existe no rodapé
    # Campos são somente leitura nesta tela (consulta + baixa).
    assert not pagina._f_desc.widget.isEnabled()


def test_contas_receber_baixa_sem_selecao_nao_chama_api(app, pumpar):
    pagina = PaginaContasReceber(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    pagina._dar_baixa()
    assert ESTADO["baixas"] == []


# ----------------------------------------------------------- plano de contas
def test_plano_contas_cadastra(app, pumpar):
    pagina = PaginaPlanoContas(_api())
    pumpar(lambda: pagina._tabela.rowCount() == 0)

    pagina._f_codigo.definir("3.1")
    pagina._f_nome.definir("Receita de Serviços")
    pagina._f_tipo.definir("receita")
    pagina._f_ativo.definir(True)
    pagina._salvar()
    pumpar(lambda: ESTADO["criados"])

    assert ESTADO["criados"][0] == {
        "codigo": "3.1",
        "nome": "Receita de Serviços",
        "tipo": "receita",
        "ativo": True,
    }


def test_botoes_reabilitados_em_ciclo_completo_de_cliques(app, pumpar):
    """Regressão P0: botões só eram reabilitados no erro, nunca no sucesso."""
    pagina = PaginaCaixa(_api())
    pumpar(lambda: pagina._caixa is None)

    pagina._btn_abrir.click()
    pumpar(lambda: pagina._caixa is not None)
    assert pagina._btn_lancar.isEnabled() and pagina._btn_fechar.isEnabled()
    assert not pagina._btn_abrir.isEnabled()

    pagina._f_tipo.definir("suprimento")
    pagina._f_valor.definir("10")
    pagina._btn_lancar.click()
    pumpar(lambda: len(ESTADO["extrato"]) == 1)
    assert pagina._btn_lancar.isEnabled()

    pagina._f_informado.definir("10")
    pagina._btn_fechar.click()
    pumpar(lambda: ESTADO["caixa"] is None)
    assert pagina._btn_abrir.isEnabled()
    assert not pagina._btn_lancar.isEnabled()

    # Segundo ciclo — antes o botão Abrir ficava morto para sempre.
    pagina._btn_abrir.click()
    pumpar(lambda: pagina._caixa is not None)
    assert pagina._btn_lancar.isEnabled()


def test_campos_sao_limpos_apos_abrir_e_fechar(app, pumpar):
    pagina = PaginaCaixa(_api())
    pagina._f_abertura.definir("100")
    pagina._f_obs_abertura.definir("troco")
    pagina._btn_abrir.click()
    pumpar(lambda: pagina._caixa is not None)
    assert pagina._f_abertura.valor() in (None, "", 0)
    assert pagina._f_obs_abertura.valor() in (None, "")

    pagina._f_informado.definir("100")
    pagina._f_obs_fech.definir("conferido")
    pagina._btn_fechar.click()
    pumpar(lambda: ESTADO["caixa"] is None)
    assert pagina._f_informado.valor() in (None, "", 0)
    assert pagina._f_obs_fech.valor() in (None, "")


def test_divergencia_recusada_nao_fecha_caixa(app, pumpar, monkeypatch):
    pagina = PaginaCaixa(_api())
    pagina._btn_abrir.click()
    pumpar(lambda: pagina._caixa is not None)
    pagina._f_informado.definir("90")  # esperado 100 → divergência -10
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.No,
    )
    pagina._btn_fechar.click()
    assert ESTADO["caixa"] is not None
    assert pagina._caixa is not None


def test_sem_divergencia_mensagem_correta(app, pumpar, monkeypatch):
    mensagens = []
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda _pai, titulo, texto, *_a, **_k: mensagens.append(texto),
    )
    pagina = PaginaCaixa(_api())
    pagina._f_abertura.definir("100")
    pagina._btn_abrir.click()
    pumpar(lambda: pagina._caixa is not None)
    pagina._f_informado.definir("100")
    pagina._btn_fechar.click()
    pumpar(lambda: ESTADO["caixa"] is None)
    assert any("sem divergência" in m for m in mensagens)


def test_423_de_usuario_bloqueado_titulo_especifico(app, monkeypatch):
    vistos = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda _pai, titulo, texto, *_a, **_k: vistos.append(str(titulo)),
    )
    pagina = PaginaCaixa(_api())
    pagina._erro("Usuário temporariamente bloqueado por excesso de tentativas.", 423)
    assert vistos[-1] == "Usuário bloqueado"


def test_fechamento_sem_valor_informado_confirma_dispensa(app, pumpar, monkeypatch):
    """Dia sem lançamento: F9 com campo vazio deve fechar usando o esperado."""
    perguntas = []
    mensagens = []
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda _pai, titulo, texto, *_a, **_k: (
            perguntas.append(texto) or QMessageBox.StandardButton.Yes
        ),
    )
    monkeypatch.setattr(
        QMessageBox, "information",
        lambda _pai, titulo, texto, *_a, **_k: mensagens.append(texto),
    )

    pagina = PaginaCaixa(_api())
    pagina._f_abertura.definir("50")
    pagina._btn_abrir.click()
    pumpar(lambda: pagina._caixa is not None)

    # Sem movimentos: saldo = 50, conferência dispensada.
    pagina._btn_fechar.click()
    pumpar(lambda: ESTADO["caixa"] is None)

    assert any("conferência dispensada" in p.lower() for p in perguntas)
    assert any("sem divergência" in m for m in mensagens)
    assert pagina._btn_abrir.isEnabled()
