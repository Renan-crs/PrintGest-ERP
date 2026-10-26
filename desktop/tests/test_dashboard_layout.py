"""Auditoria de layout do Início: sem alturas fixas, sem textos cortados.

Roda a Tela Principal em 1280x720, 1366x768 e 1920x1080 (plataforma offscreen)
e verifica, programaticamente, os critérios de aceite ligados a truncamento:

  - nenhum widget do Início usa altura fixa (`setFixedHeight`/`setFixedWidth`);
  - controles (botões/combo/menu) cabem na própria `sizeHint` — nada de metade
    do texto cortada;
  - todo `ElideLabel` que precisou encurtar tem o texto completo no tooltip;
  - o grid de KPIs reflui (mais alto em larguras estreitas).
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QToolButton, QWidget

from printgest.core.api import Api
from printgest.ui.tela_principal import TelaPrincipal
from printgest.ui.widgets import ElideLabel

_HOJE = date.today()

_RESOLUCOES = [(1280, 720), (1366, 768), (1920, 1080)]


def _handler(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path
    if caminho == "/v1/dashboard/resumo":
        dias = int(request.url.params.get("dias", 7))
        return httpx.Response(200, json={"data": {
            "filial_nome": "Matriz",
            "vendas_hoje_qtd": 12,
            "vendas_hoje_valor": "123456.78",
            "vendas_ontem_qtd": 9,
            "vendas_ontem_valor": "98765.43",
            "projetos_em_producao": 18,
            "projetos_atrasados": 3,
            "a_receber_vence_hoje": "98765.43",
            "a_receber_atrasado": "12345.67",
            "estoque_abaixo_minimo": 2,
            "entregas_hoje": [
                {"os_id": 1, "numero": 1,
                 "cliente_nome": "Gráfica Impressos Comunicação Visual Ltda ME",
                 "servico": "Cartões de visita", "prazo": _HOJE.isoformat(),
                 "status": "producao", "atrasada": False},
            ],
            "vendas_7_dias": [
                {"data": (_HOJE - timedelta(days=6 - i)).isoformat(), "valor": f"{(i + 1) * 100}.0"}
                for i in range(7)
            ],
            "faturamento_previsto": [
                {"data": (_HOJE + timedelta(days=i)).isoformat(), "valor": f"{(i + 1) * 70}.0"}
                for i in range(7)
            ],
        }})
    if caminho == "/v1/licenca":
        return httpx.Response(200, json={"data": {"status": "ativa", "modo_leitura": False}})
    if caminho == "/health":
        return httpx.Response(200, json={"status": "ok"})
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _principal() -> TelaPrincipal:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": {
        "id": 1, "nome": "Maria Silva", "login": "maria",
        "nivel_acesso": "admin", "filial_nome": "Matriz",
    }})
    return TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")


@pytest.mark.parametrize("largura,altura", _RESOLUCOES)
def test_sem_texto_cortado_nas_resolucoes(app, pumpar, largura, altura):
    principal = _principal()
    inicio = principal._pagina_inicio
    principal.resize(largura, altura)
    principal.show()
    pumpar(lambda: inicio._kpi_vendas_valor.text() != "—")
    app.processEvents()

    # 1) nenhum widget do Início usa altura fixa
    for widget in inicio.findChildren(QWidget):
        assert not (
            widget.minimumHeight() > 0
            and widget.minimumHeight() == widget.maximumHeight()
        ), f"altura fixa em {widget!r} ({largura}x{altura})"

    # 2) controles cabem na própria sizeHint
    controles = inicio.findChildren(QPushButton) + inicio.findChildren(QComboBox)
    controles += principal.findChildren(QToolButton)
    for controle in controles:
        if controle.isHidden():
            continue
        assert controle.height() + 1 >= controle.sizeHint().height(), (
            f"controle cortado: {controle.text()!r} "
            f"{controle.height()} < {controle.sizeHint().height()} ({largura}x{altura})"
        )

    # 3) qualquer ElideLabel encurtado preserva o texto completo no tooltip
    for rotulo in inicio.findChildren(ElideLabel):
        completo = rotulo.text()
        if not completo:
            continue
        if rotulo.fontMetrics().horizontalAdvance(completo) > rotulo.width():
            assert rotulo.toolTip() == completo, (
                f"elide sem tooltip: {completo!r} ({largura}x{altura})"
            )


def test_grid_de_kpis_reflui(app, pumpar):
    principal = _principal()
    inicio = principal._pagina_inicio
    pumpar(lambda: inicio._kpi_vendas_valor.text() != "—")
    grade = inicio._grade_kpi
    assert grade.count() == 3
    # mais estreito → mais linhas → mais alto que em uma linha larga
    assert grade.heightForWidth(360) > grade.heightForWidth(1600)


def test_rotulos_de_grupo_alinhados_aos_itens(app):
    from PySide6.QtCore import QPoint

    principal = _principal()
    principal.resize(1280, 720)
    principal.show()
    app.processEvents()
    app.processEvents()
    sidebar = principal._sidebar
    imagem = sidebar.grab().toImage()

    def escuro(cor) -> bool:
        return (0.299 * cor.red() + 0.587 * cor.green() + 0.114 * cor.blue()) < 180

    def primeiro_x(widget) -> int:
        topo = widget.mapTo(sidebar, QPoint(0, 0))
        for x in range(topo.x(), topo.x() + widget.width()):
            for y in range(topo.y(), topo.y() + widget.height()):
                if escuro(imagem.pixelColor(x, y)):
                    return x
        return -1

    grupos = [w for w in sidebar.findChildren(QLabel) if w.objectName() == "grupoMenu"]
    itens = [
        w for w in sidebar.findChildren(QPushButton)
        if w.property("nav") == "true" and w.isCheckable()
    ]
    assert grupos and itens
    for grupo in grupos:
        if grupo.isHidden():
            continue
        x_grupo = primeiro_x(grupo)
        if x_grupo < 0:
            continue
        # o rótulo do grupo deve começar no mesmo recuo do texto dos itens (±2px)
        assert abs(x_grupo - primeiro_x(itens[0])) <= 2, (
            f"grupo em x={x_grupo}, item em x={primeiro_x(itens[0])}"
        )
