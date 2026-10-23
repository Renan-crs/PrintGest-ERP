"""Testes do Dashboard (Tela Inicial) do desktop v2.1 — cards, RBAC, faturamento e rodapé.

Cobre os contratos do §2.2 de `telas_e_fluxos` (revisão A1–D3):
  - 3 KPIs consolidados (Vendas hoje / A receber / Projetos em produção) com
    subtexto e pluralização correta, alimentados por `GET /v1/dashboard/resumo`;
  - RBAC de cards: vendas para todos, "A receber"/faturamento gerente+,
    projetos/entregas/estoque operador+;
  - combo 7/30 dias recarrega as barras realizado × previsto;
  - indicador compacto de estoque crítico (0 itens ≠ N itens);
  - acesso rápido filtrado por perfil; filial no cabeçalho via signal;
  - colapso, atalhos e rodapé; BuscaGlobal; resumo vazio tolerado.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QScrollArea

from printgest.core.api import Api
from printgest.ui.tela_principal import TelaPrincipal

_HOJE = date.today()


def _resumo(dias: int = 7, filial: str = "Filial Matriz") -> dict:
    realizado = [
        {"data": (_HOJE - timedelta(days=i)).isoformat(), "valor": f"{i * 10 + 5}.00"}
        for i in range(dias)
    ]
    previsto = [
        {"data": (_HOJE + timedelta(days=i)).isoformat(), "valor": f"{i * 7 + 3}.00"}
        for i in range(dias)
    ]
    return {
        "filial_nome": filial,
        "vendas_hoje_qtd": 7,
        "vendas_hoje_valor": "112.40",
        "vendas_ontem_qtd": 5,
        "vendas_ontem_valor": "88.20",
        "projetos_em_producao": 3,
        "projetos_atrasados": 1,
        "a_receber_vence_hoje": "150.00",
        "a_receber_atrasado": "40.50",
        "estoque_abaixo_minimo": 4,
        "entregas_hoje": [
            {
                "os_id": 1,
                "numero": "OS-001",
                "cliente_nome": "Ana",
                "servico": "Impressão de cartões",
                "prazo": _HOJE.isoformat(),
                "status": "producao",
                "atrasada": False,
            },
            {
                "os_id": 2,
                "numero": "OS-002",
                "cliente_nome": "Biz Ltda",
                "servico": "Plotagem",
                "prazo": (_HOJE - timedelta(days=1)).isoformat(),
                "status": "producao",
                "atrasada": True,
            },
        ],
        "vendas_7_dias": realizado,
        "faturamento_previsto": previsto,
    }


def _handler(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path
    if request.method == "GET" and caminho == "/v1/dashboard/resumo":
        dias = int(request.url.params.get("dias", 7))
        return httpx.Response(200, json={"data": _resumo(dias)})
    if request.method == "GET" and caminho == "/v1/licenca":
        return httpx.Response(
            200,
            json={"data": {"status": "ativa", "modo_leitura": False}},
        )
    if request.method == "GET" and caminho == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.method == "GET" and caminho in ("/v1/clientes", "/v1/produtos", "/v1/os"):
        dados = {
            "/v1/clientes": {"data": [{"id": 1, "nome_razao": "Ana"}]},
            "/v1/produtos": {"data": [{"id": 2, "nome": "Papel A4"}]},
            "/v1/os": {"data": [{"id": 3, "numero": 12, "cliente_nome": "Ana"}]},
        }[caminho]
        return httpx.Response(
            200,
            json={"data": dados["data"], "meta": {"total": 1, "limit": 50, "offset": 0}},
        )
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _principal(usuario: dict, modo_leitura: bool = False) -> TelaPrincipal:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler))
    api.autenticar({"token": "tok", "usuario": usuario})
    return TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=modo_leitura, base_url="127.0.0.1:8000"
    )


def _textos_botoes(principal):
    return [str(b.text()) for b in principal.findChildren(QPushButton)]


def test_admin_ve_cards_reais_e_filial_no_cabecalho(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    pumpar(lambda: "112,40" in principal._pagina_inicio._kpi_vendas_valor.text())

    inicio = principal._pagina_inicio
    assert "112,40" in inicio._kpi_vendas_valor.text()
    assert inicio._kpi_vendas_sub.text() == "7 vendas · ontem: 5"
    assert "150,00" in inicio._kpi_receber_valor.text()
    assert "40,50" in inicio._kpi_receber_sub.text()
    assert inicio._kpi_projetos_valor.text() == "3"
    assert inicio._kpi_projetos_sub.text() == "1 atrasado"
    assert "4" in inicio._lbl_estoque.text()
    assert not inicio._btn_estoque.isHidden()  # com N>0 há link para o estoque

    # entregas do dia
    assert inicio._lista_entregas.count() == 2
    assert inicio._lista_entregas.item(0).text() == (
        f"Ana · Impressão de cartões · {_HOJE.isoformat()} · PRODUCAO"
    )
    # atraso não depende só da cor: o texto carrega o aviso (§1 color-not-only)
    assert inicio._lista_entregas.item(1).text().startswith("⚠ Atrasada · ")

    # faturamento realizado × previsto com 7 dias
    assert inicio._combo_dias.currentData() == 7
    assert len(inicio._barras_realizado) == 7
    assert len(inicio._barras_previsto) == 7

    # filial chega no cabeçalho pelo signal do resumo
    assert principal._lbl_filial.text() == "Filial Matriz"


def test_kpis_pluralizam_corretamente(app, pumpar):
    def _handler_um(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/dashboard/resumo":
            dados = _resumo()
            dados["vendas_hoje_qtd"] = 1
            dados["vendas_ontem_qtd"] = 0
            dados["projetos_atrasados"] = 0
            return httpx.Response(200, json={"data": dados})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"detail": "rota não esperada"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler_um))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}})
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    inicio = principal._pagina_inicio
    pumpar(lambda: inicio._kpi_vendas_sub.text() != "")
    assert inicio._kpi_vendas_sub.text() == "1 venda · ontem: 0"
    assert inicio._kpi_projetos_sub.text() == "0 atrasados"


def test_combo_dias_recarrega_faturamento(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    inicio = principal._pagina_inicio
    pumpar(lambda: len(inicio._barras_realizado) == 7)

    inicio._combo_dias.setCurrentIndex(1)  # 30 dias
    pumpar(lambda: len(inicio._barras_realizado) == 30)
    assert inicio._combo_dias.currentData() == 30
    assert len(inicio._barras_previsto) == 30


def test_caixa_ve_apenas_cards_de_vendas(app, pumpar):
    principal = _principal({"id": 1, "nome": "Zé", "login": "ze", "nivel_acesso": "caixa"})
    pumpar(lambda: "112,40" in principal._pagina_inicio._kpi_vendas_valor.text())

    inicio = principal._pagina_inicio
    assert "112,40" in inicio._kpi_vendas_valor.text()
    # cards gerenciais e operacionais ocultos para caixa
    assert not hasattr(inicio, "_kpi_receber_valor")
    assert not hasattr(inicio, "_kpi_projetos_valor")
    assert not hasattr(inicio, "_lbl_estoque")
    assert not hasattr(inicio, "_lista_entregas")
    assert not hasattr(inicio, "_combo_dias")
    assert not hasattr(inicio, "_barras_realizado")

    # acesso rápido do caixa: Nova venda + Emitir NFC-e
    textos = [b.text() for b in inicio._botoes_rapidos]
    assert textos == ["Nova venda", "Emitir NFC-e"]

    # a lateral não duplica mais as ações de criação
    botoes = _textos_botoes(principal)
    assert "Nova OS" not in botoes
    assert "Nova Venda Balcão" not in botoes
    assert "Nova OS/Orçamento" not in botoes


def test_operador_ve_cards_operacionais_mas_nao_gerenciais(app, pumpar):
    principal = _principal({"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"})
    pumpar(lambda: principal._pagina_inicio._kpi_vendas_valor.text() != "—")

    inicio = principal._pagina_inicio
    assert inicio._kpi_projetos_valor.text() == "3"
    assert inicio._lista_entregas.count() == 2
    assert "4" in inicio._lbl_estoque.text()
    assert not hasattr(inicio, "_kpi_receber_valor")  # gerencial oculto
    assert not hasattr(inicio, "_combo_dias")
    assert not hasattr(inicio, "_barras_realizado")

    textos = [b.text() for b in inicio._botoes_rapidos]
    assert textos == ["Nova venda", "Nova OS/Orçamento", "Novo cliente"]


def test_estoque_critico_zerado_estado_neutro(app, pumpar):
    def _handler_zero(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/dashboard/resumo":
            dados = _resumo()
            dados["estoque_abaixo_minimo"] = 0
            return httpx.Response(200, json={"data": dados})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"detail": "rota não esperada"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler_zero))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"}})
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    inicio = principal._pagina_inicio
    pumpar(lambda: not inicio._lbl_estoque.text().startswith("Consultando"))
    assert inicio._lbl_estoque.text() == "✓ Nenhum item abaixo do mínimo"
    assert inicio._lbl_estoque.property("role") == "success"
    assert inicio._btn_estoque.isHidden()  # sem barra nem link com 0 itens


def test_entregas_vazias_mostram_estado_vazio_com_acao(app, pumpar):
    def _handler_vazio_entregas(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/dashboard/resumo":
            dados = _resumo()
            dados["entregas_hoje"] = []
            return httpx.Response(200, json={"data": dados})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"detail": "rota não esperada"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler_vazio_entregas))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"}})
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    inicio = principal._pagina_inicio
    # estado vazio: a lista some e entra o convite à ação (§8 empty-states)
    pumpar(lambda: not inicio._vazio_entregas.isHidden())
    assert inicio._lista_entregas.isHidden()
    assert not inicio._vazio_entregas.isHidden()
    textos = [
        w.text() for w in inicio._vazio_entregas.findChildren(QLabel)
    ]
    assert "Nenhuma entrega para hoje ou atrasada." in textos
    # há uma ação de recuperação visível, não só um texto morto
    acoes = [b for b in inicio._vazio_entregas.findChildren(QPushButton)]
    assert acoes and acoes[0].text() == "Ver Ordens de Serviço"


def test_faturamento_vazio_mostra_convite(app, pumpar):
    def _handler_sem_fat(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/dashboard/resumo":
            dados = _resumo()
            dados["vendas_7_dias"] = []
            dados["faturamento_previsto"] = []
            return httpx.Response(200, json={"data": dados})
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"detail": "rota não esperada"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler_sem_fat))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}})
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    inicio = principal._pagina_inicio
    pumpar(lambda: "sem movimenta" in inicio._lbl_grafico.text().lower())
    assert "Sem movimentação no período" in inicio._lbl_grafico.text()


def test_acesso_rapido_navega_para_cliente(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    pumpar(lambda: principal._pagina_inicio._kpi_vendas_valor.text() != "—")
    botoes = {b.text(): b for b in principal._pagina_inicio._botoes_rapidos}
    assert set(botoes) == {"Nova venda", "Nova OS/Orçamento", "Novo cliente", "Emitir NFC-e"}
    navegados = []
    principal.navegado.connect(lambda item_id: navegados.append(item_id))
    botoes["Novo cliente"].click()
    pumpar(lambda: principal._stack_paginas.currentWidget() is not principal._pagina_inicio)
    assert principal._stack_paginas.currentWidget() is principal._paginas["cliente"]
    assert navegados == ["cliente"]


def test_modo_leitura_banner_e_licenca_vermelha(app, pumpar):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}, modo_leitura=True
    )
    pumpar(lambda: principal._lbl_licenca.property("role") == "erro")
    banners = [w for w in principal.findChildren(QLabel) if w.objectName() == "bannerLeitura"]
    assert len(banners) == 1
    assert "modo leitura" in banners[0].text().lower()
    assert principal._lbl_licenca.text() == "● Licença"
    assert principal._lbl_licenca.property("role") == "erro"


def test_licenca_ativa_verde(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    pumpar(lambda: principal._lbl_licenca.property("role") == "success")
    assert principal._lbl_licenca.text() == "● Licença"
    assert principal._lbl_licenca.property("role") == "success"


def test_cabecalho_sem_duplicar_usuario_nem_daemon(app):
    principal = _principal({"id": 1, "nome": "Ana Silva", "login": "ana", "nivel_acesso": "admin"})
    textos = _textos_botoes(principal)
    # badge técnico "Daemon: ..." e botão "Sair" solto deram lugar ao menu único
    assert not any("Daemon" in t for t in textos)
    assert "Sair" not in textos
    labels = [w.text() for w in principal.findChildren(QLabel)]
    assert "● Servidor local" in labels
    # menu de usuário único com iniciais + nome + perfil
    assert "AS" in principal._menu_usuario.text()
    assert "Ana Silva" in principal._menu_usuario.text()
    assert "Admin" in principal._menu_usuario.text()
    acoes = [a.text() for a in principal._menu_usuario.menu().actions() if a.text()]
    assert acoes == ["Preferências", "Trocar senha", "Sair"]


def test_cabecalho_nao_repete_perfil_igual_ao_nome(app):
    principal = _principal(
        {"id": 1, "nome": "Administrador", "login": "admin", "nivel_acesso": "admin"}
    )
    texto = principal._menu_usuario.text()
    assert "AD" in texto
    assert texto.count("Admin") == 1
    assert "·" not in texto


def test_servidor_local_deixa_ip_apenas_no_tooltip(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    pumpar(lambda: "online" in principal._lbl_conexao.text())
    assert principal._lbl_servidor.text() == "● Servidor local"
    assert "127.0.0.1:8000" in principal._lbl_servidor.toolTip()
    assert "127.0.0.1" not in principal._lbl_servidor.text()


def test_conteudo_do_inicio_tem_scroll(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    assert principal._pagina_inicio._scroll.widgetResizable() is True
    scrolls = principal._pagina_inicio.findChildren(QScrollArea)
    assert scrolls


def test_colapso_da_lateral(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    assert principal._sidebar.width() == 224
    principal._btn_colapso.click()
    assert principal._sidebar.width() == 64
    assert principal._btn_colapso.text() == "»"
    principal._btn_colapso.click()
    assert principal._sidebar.width() == 224


def test_atalhos_de_criacao_so_no_acesso_rapido(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    botoes = _textos_botoes(principal)
    assert "Nova Venda Balcão" not in botoes
    assert "Nova OS" not in botoes
    rapidos = [b.text() for b in principal._pagina_inicio._botoes_rapidos]
    assert "Nova venda" in rapidos
    assert "Nova OS/Orçamento" in rapidos


def test_rodape_relogio_estacao_e_conexao(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    pumpar(lambda: "online" in principal._lbl_conexao.text())
    import re

    assert re.match(r"^\d{2}:\d{2}:\d{2}$", principal._lbl_relogio.text())
    assert principal._lbl_conexao.text() == "● online"


def test_busca_global_sugere_e_navega(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    busca = principal._busca
    busca._campo.setText("Ana")
    pumpar(lambda: busca._sugestoes.count() >= 3)
    assert not busca._sugestoes.isHidden()

    navegados = []
    busca.navegar.connect(lambda item_id: navegados.append(item_id))

    alvo = None
    for i in range(busca._sugestoes.count()):
        dados = busca._sugestoes.item(i).data(Qt.ItemDataRole.UserRole) or {}
        if dados.get("modulo") == "cliente":
            alvo = busca._sugestoes.item(i)
            break
    assert alvo is not None
    busca._escolher(alvo)
    assert navegados == ["cliente"]


def test_sem_conexao_mostra_alerta_e_libera_banner(app, pumpar):
    def _handler_off(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/dashboard/resumo":
            return httpx.Response(200, json={"data": _resumo()})
        return httpx.Response(503, json={"detail": "indisponível"})

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_handler_off))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}})
    principal = TelaPrincipal(api, usuario=api.usuario, base_url="127.0.0.1:8000")
    inicio = principal._pagina_inicio
    pumpar(lambda: not inicio._alerta_conexao.isHidden())
    assert "Servidor local" in inicio._alerta_conexao.text()
    assert principal._lbl_servidor.property("role") == "error"


def _vazio_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}},
    )


def test_dashboard_tolera_resumo_vazio(app, pumpar):
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_vazio_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}})
    principal = TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=False, base_url="127.0.0.1:8000"
    )
    pumpar(lambda: not principal._pagina_inicio._lbl_estoque.text().startswith("Aguardando"))
    assert principal._pagina_inicio._kpi_vendas_valor.text() == "—"
    assert not principal._pagina_inicio._lbl_estoque.text().startswith("Aguardando")
