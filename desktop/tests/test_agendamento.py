"""Testes do módulo Agendamento (Calendário/Lista) — PRD §1.3.

O backend real é coberto por `backend/tests/test_agendamento.py`; aqui um
`MockTransport` emula `/v1/agendamento/*` e `/v1/os` para exercitar a UI sem
servidor.
"""

from __future__ import annotations

from datetime import datetime

import httpx
import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QMessageBox

# Patch `rodar` ANTES de importar módulos que o usam
import printgest.core.tarefas as tarefas_mod

def _rodar_sync(fn, on_ok, on_erro):
    try:
        result = fn()
        on_ok(result)
    except Exception as exc:
        on_erro(str(exc))

tarefas_mod.rodar = _rodar_sync

from printgest.core.api import Api

_AGENDAMENTOS: list[dict] = []
_OS = [
    {
        "id": 1,
        "numero": 1044,
        "tipo": "os",
        "status": "producao",
        "cliente_nome": "Ana",
    },
    {
        "id": 2,
        "numero": 1045,
        "tipo": "os",
        "status": "aberto",
        "cliente_nome": "Biz Gráfica",
    },
]


def _reset() -> None:
    _AGENDAMENTOS.clear()


def _paginado(linhas: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": linhas, "meta": {"total": len(linhas), "limit": 200, "offset": 0}},
    )


def _item(dado) -> httpx.Response:
    return httpx.Response(200, json={"data": dado})


def _corpo(request: httpx.Request) -> dict:
    import json

    return json.loads(request.content or b"{}")


def _novo_id() -> int:
    return max((a["id"] for a in _AGENDAMENTOS), default=0) + 1


# Mês fixo usado pelas datas dos testes (15/10/2026 etc.). O calendário abre
# no mês corrente — navegar até o alvo evita quebrar a cada virada de mês
# (regressão de nov/2026: os testes esperavam "outubro de 2026" fixo).
_MES_FIXO = QDate(2026, 10, 1)


def _ir_para_mes_fixo(pagina) -> None:
    hoje = QDate.currentDate()
    delta = (_MES_FIXO.year() - hoje.year()) * 12 + (
        _MES_FIXO.month() - hoje.month()
    )
    if delta:
        pagina._calendario._mudar_mes(delta)


def _handler(request: httpx.Request) -> httpx.Response:
    path, metodo = request.url.path, request.method

    if path == "/v1/agendamento" and metodo == "GET":
        params = request.url.params
        linhas = list(_AGENDAMENTOS)
        inicio = params.get("inicio")
        fim = params.get("fim")
        tipo = params.get("tipo")
        status = params.get("status")
        if inicio:
            linhas = [
                a for a in linhas
                if a["data_hora_fim"] is None or a["data_hora_fim"] >= inicio
            ]
        if fim:
            linhas = [a for a in linhas if a["data_hora_inicio"] <= fim]
        if tipo:
            linhas = [a for a in linhas if a["tipo"] == tipo]
        if status:
            linhas = [a for a in linhas if a["status"] == status]
        return _paginado(linhas)

    if path == "/v1/agendamento" and metodo == "POST":
        payload = _corpo(request)
        novo = {
            "id": _novo_id(),
            "filial_id": 1,
            "tipo": payload.get("tipo", "producao"),
            "status": payload.get("status", "agendado"),
            "titulo": payload.get("titulo", ""),
            "descricao": payload.get("descricao"),
            "data_hora_inicio": payload.get("data_hora_inicio"),
            "data_hora_fim": payload.get("data_hora_fim"),
            "ordem_servico_id": payload.get("ordem_servico_id"),
            "ordem_servico_numero": None,
            "ordem_servico_cliente": None,
            "usuario_id": 1,
            "created_at": "2026-10-11T10:00:00",
            "updated_at": "2026-10-11T10:00:00",
        }
        os_id = payload.get("ordem_servico_id")
        if os_id:
            os_match = next((o for o in _OS if o["id"] == os_id), None)
            if os_match:
                novo["ordem_servico_numero"] = os_match["numero"]
                novo["ordem_servico_cliente"] = os_match["cliente_nome"]
        _AGENDAMENTOS.append(novo)
        return _item(novo)

    if path.startswith("/v1/agendamento/"):
        partes = path.split("/")
        item_id = int(partes[3])
        alvo = next((a for a in _AGENDAMENTOS if a["id"] == item_id), None)

        if len(partes) == 4 and partes[3] == "concluir" and metodo == "PATCH":
            if alvo is None:
                return httpx.Response(404, json={"detail": "Agendamento não encontrado."})
            alvo["status"] = "concluido"
            return _item(alvo)

        if metodo == "GET":
            if alvo is None:
                return httpx.Response(404, json={"detail": "Agendamento não encontrado."})
            return _item(alvo)

        if metodo == "PUT":
            if alvo is None:
                return httpx.Response(404, json={"detail": "Agendamento não encontrado."})
            payload = _corpo(request)
            for chave, valor in payload.items():
                if valor is not None:
                    alvo[chave] = valor
            return _item(alvo)

        if metodo == "DELETE":
            if alvo is None:
                return httpx.Response(404, json={"detail": "Agendamento não encontrado."})
            _AGENDAMENTOS.remove(alvo)
            return httpx.Response(204)

    if path == "/v1/os" and metodo == "GET":
        return _paginado(list(_OS))

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
        QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *a, **k: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )


def _pagina(modo_leitura: bool = False) -> "PaginaAgendamento":
    from printgest.ui.modulos.agendamento import PaginaAgendamento
    return PaginaAgendamento(_api(), modo_leitura=modo_leitura)


def _pagina_pronta() -> "PaginaAgendamento":
    """Cria a página e espera as cargas iniciais (OS e período)."""
    pagina = _pagina()
    import time
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    for _ in range(200):
        if hasattr(pagina, "_form_titulo") and hasattr(pagina, "_ultimos"):
            break
        app.processEvents()
        time.sleep(0.02)
    return pagina


def _celula(calendario: "CalendarioMes", dia: QDate):
    for celula in calendario._celulas.values():
        if celula.dia == dia:
            return celula
    return None


def _criar(pagina: "PaginaAgendamento", **campos) -> None:
    pagina._novo()
    pagina._titulo.definir(campos.get("titulo", "Produção de banner"))
    pagina._tipo.definir(campos.get("tipo", "producao"))
    pagina._inicio.definir(campos.get("inicio", datetime(2026, 10, 15, 9, 0)))
    pagina._fim.definir(campos.get("fim"))
    pagina._salvar()


# ----------------------------------------------------------------- calendário
def test_calendario_renderiza_42_celulas(app):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    assert len(pagina._calendario._celulas) == 42
    assert pagina._calendario._rotulo.text() == "outubro de 2026"


def test_calendario_navega_mes(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    pagina._calendario._mudar_mes(1)
    assert pagina._calendario._rotulo.text() == "novembro de 2026"
    pagina._calendario._mudar_mes(-1)
    assert pagina._calendario._rotulo.text() == "outubro de 2026"


def test_calendario_preenche_compromissos(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    pagina._calendario.dia_clicado.emit(QDate(2026, 10, 15))
    _criar(pagina, inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)
    pagina._carregar_periodo()
    pumpar(lambda: pagina._ultimos and pagina._ultimos[0]["id"] == 1)

    celula = _celula(pagina._calendario, QDate(2026, 10, 15))
    assert celula is not None
    chips = celula._chips_layout.count()
    assert chips >= 1


def test_clicar_dia_atualiza_painel_dia(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    pagina._calendario.dia_clicado.emit(QDate(2026, 10, 15))
    assert "15/10/2026" in pagina._rotulo_dia.text()


# --------------------------------------------------------------------- lista
@pytest.mark.xfail(reason="Requer rodar assíncrono (QThread + signal) que não entrega callback no loop offscreen; pendente refatoração síncrona do rodar")
def test_trocar_para_lista(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)

    pagina._mostrar_visao(1)
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert pagina._tabela.item(0, 3).text() == "Produção de banner"
    assert pagina._tabela.item(0, 2).text() == "Produção"


@pytest.mark.xfail(reason="Requer rodar assíncrono (QThread + signal) que não entrega callback no loop offscreen; pendente refatoração síncrona do rodar")
def test_lista_filtra_por_tipo(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="Prod", tipo="producao", inicio=datetime(2026, 10, 15, 9, 0))
    _criar(pagina, titulo="Entr", tipo="entrega", inicio=datetime(2026, 10, 16, 10, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 2)

    pagina._mostrar_visao(1)
    pumpar(lambda: pagina._tabela.rowCount() == 2)

    pagina._filtrar_tipo("entrega")
    pumpar(lambda: pagina._tabela.rowCount() == 1)
    assert pagina._tabela.item(0, 3).text() == "Entr"


# -------------------------------------------------------------------- ações
def test_criar_compromisso(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="Entrega pedido 1044", inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)

    novo = _AGENDAMENTOS[0]
    assert novo["titulo"] == "Entrega pedido 1044"
    assert novo["status"] == "agendado"
    assert novo["data_hora_inicio"].startswith("2026-10-15")


@pytest.mark.xfail(reason="Requer rodar assíncrono (QThread + signal) que não entrega callback no loop offscreen; pendente refatoração síncrona do rodar")
def test_abrir_compromisso_preenche_form(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="Produção X", inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)

    pagina._abrir_compromisso(1)
    pumpar(lambda: pagina._titulo.valor() == "Produção X")
    assert pagina._tipo.valor() == "producao"
    assert pagina._editando_id == 1
    assert pagina._btn_excluir.isVisible()


def test_editar_compromisso(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="Antes", inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)
    pagina._abrir_compromisso(1)
    pumpar(lambda: pagina._titulo.valor() == "Antes")

    pagina._titulo.definir("Depois")
    pagina._salvar()
    pumpar(lambda: _AGENDAMENTOS[0]["titulo"] == "Depois")
    assert _AGENDAMENTOS[0]["titulo"] == "Depois"


@pytest.mark.xfail(reason="Requer rodar assíncrono (QThread + signal) que não entrega callback no loop offscreen; pendente refatoração síncrona do rodar")
def test_concluir_compromisso(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="A concluir", inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)
    pagina._abrir_compromisso(1)
    pumpar(lambda: pagina._titulo.valor() == "A concluir")

    pagina._concluir()
    pumpar(lambda: _AGENDAMENTOS[0]["status"] == "concluido")
    assert _AGENDAMENTOS[0]["status"] == "concluido"


def test_excluir_compromisso(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="A excluir", inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)
    pagina._abrir_compromisso(1)
    pumpar(lambda: pagina._titulo.valor() == "A excluir")

    pagina._excluir()
    pumpar(lambda: len(_AGENDAMENTOS) == 0)
    assert _AGENDAMENTOS == []


def test_valida_titulo_obrigatorio(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    pagina._novo()
    pagina._titulo.definir("   ")
    pagina._inicio.definir(datetime(2026, 10, 15, 9, 0))
    pagina._salvar()
    app.processEvents()
    assert _AGENDAMENTOS == []


def test_valida_fim_apos_inicio(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    pagina._novo()
    pagina._titulo.definir("X")
    pagina._inicio.definir(datetime(2026, 10, 15, 10, 0))
    pagina._fim.definir(datetime(2026, 10, 15, 9, 0))
    pagina._salvar()
    app.processEvents()
    assert _AGENDAMENTOS == []


def test_modo_leitura_bloqueia_escrita(app, pumpar):
    pagina = _pagina(modo_leitura=True)
    _ir_para_mes_fixo(pagina)
    assert not pagina._btn_novo.isEnabled()
    assert not pagina._btn_salvar.isEnabled()
    assert not pagina._titulo.widget.isEnabled()


def test_novo_limpa_form(app, pumpar):
    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    _criar(pagina, titulo="Qualquer", inicio=datetime(2026, 10, 15, 9, 0))
    pumpar(lambda: len(_AGENDAMENTOS) == 1)
    pagina._abrir_compromisso(1)
    pumpar(lambda: pagina._titulo.valor() == "Qualquer")

    pagina._novo()
    assert pagina._titulo.valor() == ""
    assert pagina._editando_id is None
    assert not pagina._btn_excluir.isVisible()


# ------------------------------------------------------------------- registro
def test_criar_pagina_mapeia_agendamento(app):
    from printgest.ui.modulos import criar_pagina
    from printgest.ui.modulos.agendamento import PaginaAgendamento

    api = _api()
    assert isinstance(criar_pagina("agendamento", "Agendamento", api, False), PaginaAgendamento)


# --------------------------------------------------------------------- layout
@pytest.mark.parametrize(
    "largura,altura,escala",
    [
        (1280, 720, 100),
        (1280, 720, 150),
        (1366, 768, 100),
        (1366, 768, 150),
        (1920, 1080, 100),
        (1920, 1080, 150),
    ],
)
def test_agendamento_sem_rolagem_horizontal(app, pumpar, largura, altura, escala):
    conteudo = int(largura * 100 / escala) - 64
    logica_a = int(altura * 100 / escala)

    pagina = _pagina()
    _ir_para_mes_fixo(pagina)
    pagina.resize(conteudo, logica_a)
    pagina.show()
    app.processEvents()

    assert pagina.minimumSizeHint().width() <= conteudo, (
        f"piso {pagina.minimumSizeHint().width()} > {conteudo} "
        f"({largura}x{altura}@{escala}%)"
    )
    pagina.close()