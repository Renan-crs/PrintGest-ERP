"""Smoke da Tela Principal: navegação v2.1, RBAC ocultando itens e banner de modo leitura."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from PySide6.QtWidgets import QLabel, QPushButton

from printgest.core.api import Api
from printgest.ui.modulos.em_construcao import PaginaEmConstrucao
from printgest.ui.modulos.categorias import PaginaCategorias
from printgest.ui.modulos.estoque import PaginaEstoque
from printgest.ui.modulos.funcionarios import PaginaFuncionarios
from printgest.ui.modulos.relatorios import PaginaRelatorios
from printgest.ui import tela_principal as tela_principal_mod
from printgest.ui.tela_principal import (
    ITEM_INICIO,
    TelaPrincipal,
    fracao_tolerancia,
    mensagem_tolerancia,
    tempo_restante,
)
from printgest.ui.widgets import formatar_datahora

_CLIENTES = [
    {"id": 1, "nome_razao": "Ana", "tipo_pessoa": "pf", "cpf_cnpj": "123", "celular": "1"},
    {"id": 2, "nome_razao": "Biz Ltda", "tipo_pessoa": "pj", "cpf_cnpj": "99", "celular": "2"},
]


def _cliente_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "GET" and request.url.path == "/v1/clientes":
        return httpx.Response(
            200,
            json={"data": _CLIENTES, "meta": {"total": len(_CLIENTES), "limit": 50, "offset": 0}},
        )
    return httpx.Response(404, json={"detail": "rota não esperada"})


def _principal(
    usuario: dict, modo_leitura: bool = False, situacao: dict | None = None
) -> TelaPrincipal:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_cliente_handler))
    api.autenticar({"token": "tok", "usuario": usuario})
    return TelaPrincipal(
        api,
        usuario=api.usuario,
        modo_leitura=modo_leitura,
        base_url="127.0.0.1:8000",
        situacao_licenca=situacao,
    )


def _textos_botoes(principal):
    return [str(b.text()) for b in principal.findChildren(QPushButton)]


def test_abre_no_inicio_com_menu_visivel(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    assert principal._stack_paginas.currentWidget() is principal._pagina_inicio
    botoes = _textos_botoes(principal)
    assert "PDV" in botoes
    assert "Projetos" in botoes
    assert "Clientes" in botoes
    assert "Configurações" in botoes  # SISTEMA só para admin


def test_caixa_ve_pdv_financeiro_e_fiscal(app):
    principal = _principal({"id": 1, "nome": "Zé", "login": "ze", "nivel_acesso": "caixa"})
    botoes = _textos_botoes(principal)
    assert "PDV" in botoes
    assert "Financeiro" in botoes
    assert "Fiscal" in botoes
    assert "Clientes" not in botoes
    assert "Projetos" not in botoes
    assert "Fornecedores" not in botoes
    assert "Configurações" not in botoes


def test_operador_nao_ve_gestao_na_lateral(app):
    principal = _principal({"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"})
    botoes = _textos_botoes(principal)
    assert "PDV" in botoes and "Projetos" in botoes and "Clientes" in botoes
    assert "Fornecedores" not in botoes
    assert "Financeiro" not in botoes
    assert "Fiscal" not in botoes
    assert "Configurações" not in botoes


def test_caixa_nao_tem_acesso_a_clientes(app):
    principal = _principal({"id": 1, "nome": "Zé", "login": "ze", "nivel_acesso": "caixa"})
    principal._navegar("cliente")
    assert principal._stack_paginas.currentWidget() is principal._pagina_inicio


def test_operador_nao_tem_acesso_a_financeiro(app):
    principal = _principal({"id": 1, "nome": "Jo", "login": "jo", "nivel_acesso": "operador"})
    principal._navegar("financeiro")
    assert principal._stack_paginas.currentWidget() is principal._pagina_inicio


def test_navegar_para_clientes_carrega_grade(app, pumpar):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "operador"})
    principal._navegar("cliente")
    pumpar(lambda: principal._paginas["cliente"]._tabela.rowCount() == 2)
    assert principal._stack_paginas.currentWidget() is principal._paginas["cliente"]


def test_navegar_para_projetos_abre_o_quadro(app):
    # usa handler que responde 200 para qualquer rota (a nova tela carrega o
    # quadro e os cartões no construtor; um 404 abriria QMessageBox modal e
    # travaria o próximo pump).
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_vazio_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "operador"}})
    principal = TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=False, base_url="127.0.0.1:8000"
    )
    principal._navegar("projetos")
    from printgest.ui.modulos.projetos import PaginaProjetos

    assert isinstance(principal._stack_paginas.currentWidget(), PaginaProjetos)


def test_modo_leitura_exibe_banner(app):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}, modo_leitura=True
    )
    banners = [w for w in principal.findChildren(QLabel) if w.objectName() == "bannerLeitura"]
    assert len(banners) >= 1


def test_sair_emite_logout_e_limpa_sessao(app):
    principal = _principal({"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"})
    saidas = []
    principal.solicitado_logout.connect(lambda: saidas.append(True))
    principal._sair()
    assert saidas == [True]
    assert principal._api.autenticado is False


def _vazio_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [], "meta": {"total": 0, "limit": 50, "offset": 0}},
    )


def test_navega_por_todo_o_menu_sem_erro(app):
    from printgest.core.rbac import MENU
    from printgest.ui.modulos.clientes import PaginaClientes
    from printgest.ui.modulos.configuracao import PaginaConfiguracoes
    from printgest.ui.modulos.financeiro import PaginaFinanceiro
    from printgest.ui.modulos.fiscal import PaginaFiscal
    from printgest.ui.modulos.fornecedores import PaginaFornecedores
    from printgest.ui.modulos.projetos import PaginaProjetos
    from printgest.ui.modulos.produtos import PaginaProdutos, PaginaServicos
    from printgest.ui.modulos.venda_balcao import PaginaVendaBalcao

    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(_vazio_handler))
    api.autenticar({"token": "tok", "usuario": {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}})
    principal = TelaPrincipal(
        api, usuario=api.usuario, modo_leitura=False, base_url="127.0.0.1:8000"
    )
    from printgest.ui.modulos.agendamento import PaginaAgendamento
    from printgest.ui.modulos.em_construcao import PaginaEmConstrucao
    esperadas = {
        "pdv": PaginaVendaBalcao,
        "projetos": PaginaProjetos,
        "agendamento": PaginaAgendamento,
        "cliente": PaginaClientes,
        "fornecedor": PaginaFornecedores,
        "produto": PaginaProdutos,
        "servico": PaginaServicos,
        "categoria": PaginaCategorias,
        "funcionario": PaginaFuncionarios,
        "financeiro": PaginaFinanceiro,
        "fiscal": PaginaFiscal,
        "estoque": PaginaEstoque,
        "relatorios": PaginaRelatorios,
        "configuracoes": PaginaConfiguracoes,
    }
    visitadas = set()

    for _grupo, itens in MENU:
        for item in itens:
            principal._navegar(item["id"])
            pagina = principal._stack_paginas.currentWidget()
            visitadas.add(type(pagina))
            assert isinstance(pagina, esperadas[item["id"]]), item["id"]

    for esperada in esperadas.values():
        assert esperada in visitadas


def test_configuracoes_apenas_admin(app):
    gerente = _principal({"id": 1, "nome": "Ge", "login": "ge", "nivel_acesso": "gerente"})
    botoes = _textos_botoes(gerente)
    assert "Configurações" not in botoes
    gerente._navegar("configuracoes")
    assert gerente._stack_paginas.currentWidget() is gerente._pagina_inicio


# ------------------------------- indicador de licença por estado (E5 do plano)


def test_texto_e_estilo_licenca_por_estado():
    assert TelaPrincipal._texto_licenca({"estado": "tolerancia"}, False) == (
        "Licença em tolerância"
    )
    assert TelaPrincipal._estilo_licenca({"estado": "tolerancia"}, False) == "atencao"
    assert TelaPrincipal._estilo_licenca({"estado": "revogada"}, False) == "erro"
    assert TelaPrincipal._estilo_licenca({"estado": "leitura"}, False) == "erro"
    assert TelaPrincipal._estilo_licenca({"estado": "ativa"}, False) == "success"
    # retrocompatível com payload antigo (sem o campo `estado`)
    assert TelaPrincipal._texto_licenca({"status": "ativa"}, False) == "Licença Ativa"
    assert TelaPrincipal._estilo_licenca({"status": "ativa"}, False) == "success"


def test_detalhe_licenca_inclui_motivo_e_diagnostico():
    detalhe = TelaPrincipal._detalhe_texto(
        {
            "estado": "tolerancia",
            "motivo": "Sem contato com o RedGest; operando normalmente em tolerância.",
            "chave": "************1045",
            "expira_em": "2026-10-18T09:00:00+00:00",
            "limite_ativacoes": 5,
            "ativacoes_realizadas": 2,
            "tolerancia_expira_em": "2026-10-21T09:00:00+00:00",
            "ultima_tentativa_em": "2026-10-18T10:00:00+00:00",
            "ultimo_erro": "RedGest inacessível (ConnectError)",
        },
        False,
    )
    assert "tolerância." in detalhe
    assert "Chave: ************1045" in detalhe
    assert "Estações autorizadas: 5 (em uso: 2)" in detalhe
    assert "Válida até: 18/10/2026 09:00" in detalhe
    assert "Tolerância até: 21/10/2026 09:00" in detalhe
    assert "Última verificação: 18/10/2026 10:00" in detalhe
    assert "Último erro: RedGest inacessível (ConnectError)" in detalhe


# ------------- banner progressivo de tolerância (E5 §9.3 da doc de integração)


def _tolerancia(horas: int = 48) -> dict:
    """Situação `tolerancia` com prazos relativos ao agora (evita data fixa)."""
    fim = datetime.now(timezone.utc) + timedelta(hours=horas)
    return {
        "estado": "tolerancia",
        "motivo": "Sem contato com o RedGest.",
        "chave": "************1045",
        "expira_em": (fim - timedelta(hours=72)).isoformat(),
        "tolerancia_expira_em": fim.isoformat(),
        "ultimo_erro": "RedGest inacessível (ConnectError)",
    }


def test_banner_tolerancia_aparece_com_prazo_e_restante(app):
    sit = _tolerancia(horas=48)
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}, situacao=sit
    )
    assert not principal._banner_tol.isHidden()
    texto = principal._lbl_tol.text()
    assert "Sem conexão com o servidor de licenças" in texto
    assert formatar_datahora(sit["tolerancia_expira_em"]) in texto
    assert principal._lbl_tol_restante.text().startswith("Restam ")
    assert "dia" in principal._lbl_tol_restante.text()
    assert 0 < principal._barra_tol.value() <= 1000
    assert principal._timer_tolerancia.isActive()


def test_banner_tolerancia_oculto_quando_licenca_ativa(app):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
        situacao={"estado": "ativa", "status": "ativa"},
    )
    assert principal._banner_tol.isHidden()
    assert not principal._timer_tolerancia.isActive()


def test_banner_tolerancia_oculto_em_modo_leitura(app):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
        modo_leitura=True,
        situacao=_tolerancia(),
    )
    assert principal._banner_tol.isHidden()


def test_banner_tolerancia_reage_a_mudanca_de_estado(app):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
        situacao=_tolerancia(),
    )
    assert not principal._banner_tol.isHidden()

    # revalidação bem-sucedida em background: sai de `tolerancia` sem reabrir a tela
    principal._licenca({"estado": "ativa", "status": "ativa"})
    assert principal._banner_tol.isHidden()
    assert not principal._timer_tolerancia.isActive()


def test_banner_tolerancia_persiste_se_o_daemon_local_cai(app):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
        situacao=_tolerancia(),
    )
    texto = principal._lbl_tol.text()

    # falta de resposta do daemon local é desconhecimento, não licença nova
    principal._sem_licenca("ConnectError")
    assert not principal._banner_tol.isHidden()
    assert principal._lbl_tol.text() == texto


def test_atualizar_tolerancia_recompoe_o_countdown_sem_rede(app, monkeypatch):
    principal = _principal(
        {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"},
        situacao=_tolerancia(horas=2),
    )
    prazo_antes = principal._lbl_tol.text()

    # simula o tick de 1 min logo após um novo GET (situação com prazo distante),
    # sem rede: o relógio é fixado para o resultado ser determinístico
    principal._situacao_licenca = {
        "estado": "tolerancia",
        "expira_em": "2026-10-18T09:00:00+00:00",
        "tolerancia_expira_em": "2026-10-21T09:00:00+00:00",
    }
    monkeypatch.setattr(
        tela_principal_mod,
        "_agora_utc",
        lambda: datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
    )
    principal._atualizar_tolerancia()
    assert principal._lbl_tol.text() != prazo_antes
    assert principal._lbl_tol_restante.text() == "Restam 2 dias e 21 h"


def test_tempo_restante_formata_dias_horas_minutos():
    agora = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    assert tempo_restante("2026-10-21T09:00:00+00:00", agora) == "2 dias e 21 h"
    assert tempo_restante("2026-10-19T13:00:00+00:00", agora) == "1 dia e 1 h"
    assert tempo_restante("2026-10-18T15:12:00Z", agora) == "3 h e 12 min"
    assert tempo_restante("2026-10-18T12:08:30+00:00", agora) == "8 min"
    assert tempo_restante("2026-10-18T11:00:00+00:00", agora) == "menos de 1 min"
    assert tempo_restante(None, agora) == ""
    assert tempo_restante("nao-e-data", agora) == ""


def test_fracao_tolerancia_avanca_na_janela():
    sit = {
        "expira_em": "2026-10-18T09:00:00+00:00",
        "tolerancia_expira_em": "2026-10-21T09:00:00+00:00",
    }
    meio = datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)
    assert fracao_tolerancia(sit, meio) == pytest.approx(0.5)
    # tolerância esgotada -> 0 (valor não fica negativo)
    depois = datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
    assert fracao_tolerancia(sit, depois) == 0.0
    # sem vigência (vitalícia): não há janela de tolerância a desenhar
    assert (
        fracao_tolerancia({"tolerancia_expira_em": sit["tolerancia_expira_em"]}, meio)
        is None
    )


def test_mensagem_tolerancia_traz_o_prazo_do_documento():
    texto = mensagem_tolerancia({"tolerancia_expira_em": "2026-10-21T09:00:00+00:00"})
    assert texto == (
        "Sem conexão com o servidor de licenças. O PrintGest continuará "
        "funcionando normalmente até 21/10/2026 09:00."
    )
