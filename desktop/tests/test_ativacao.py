"""Tela 1.2 — Ativação: fluxo, máscaras, estados e acessibilidade (revisão out/2026).

Cobre o fluxo com `httpx.MockTransport` (sem daemon real):
- chave aceita no formato XXXX-XXXX-XXXX-XXXX; digitação normaliza e insere hífens;
- Contrato B: máscara de CNPJ + dígito verificador em linha (D4);
- os três botões têm rótulo, altura >= 40 px e nome acessível (A1);
- erro do servidor aparece junto dos campos e não trava o fluxo (C6);
- sucesso mostra o resumo (D1) e só emite `ativada` no "Entrar";
- Esc pede confirmação (D5); diagnóstico do servidor local é honesto (D3).
"""

from __future__ import annotations

import json

import httpx
from PySide6.QtWidgets import QLineEdit, QMessageBox, QPushButton

from printgest.core.api import Api
from printgest.ui.ativacao import AtivacaoWindow

_RESPOSTA_ATIVA = {
    "status": "ativa",
    "modo_leitura": False,
    "plano": "ANUAL",
    "expira_em": "2027-10-19T00:56:26",
}
_CHAVE = "A3F1-9C2B-77DE-1045"
_CNPJ_VALIDO = "11.222.333/0001-81"


def _janela(handler, contrato: str = "c") -> AtivacaoWindow:
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    return AtivacaoWindow(api, token="tok", contrato=contrato)


def _botao(janela: AtivacaoWindow, trecho: str) -> QPushButton:
    for b in janela.findChildren(QPushButton):
        if trecho in b.text():
            return b
    raise AssertionError(f"botão {trecho!r} não encontrado")


# ------------------------------------------------------------- botões (A1)


def test_botoes_tem_rotulo_altura_e_nome_acessivel(app):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    janela.show()
    app.processEvents()
    for trecho in ("Ativar licença", "Testar conexão", "Sair"):
        b = _botao(janela, trecho)
        assert b.height() >= 40
        assert b.accessibleName() == b.text()
        assert b.isVisibleTo(janela.centralWidget())


def test_atalhos_sao_parte_do_rotulo(app):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    assert "F10" in _botao(janela, "Ativar licença").text()
    assert "Esc" in _botao(janela, "Sair").text()


# ------------------------------------------------------------ chave (C)


def test_digitacao_formata_a_chave(app):
    janela = _janela(lambda r: httpx.Response(200, json={"data": _RESPOSTA_ATIVA}))
    janela._campo_chave.setText("a3f19c2b77de1045")
    assert janela._campo_chave.text() == _CHAVE


def test_chave_incompleta_nao_chama_api(app):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    janela._campo_chave.setText("A3F1-9C2B")  # 8 caracteres: incompleta
    janela._ativar()

    # O diagnóstico automático pode ter chamado /health; a ATIVAÇÃO não pode.
    assert all(c == "/health" for c in chamadas)
    assert "Informe a chave completa" in janela._erro_chave.text()
    assert not janela._erro_chave.isHidden()  # visível dentro do cartão


def test_chave_completa_ativa_e_mostra_resumo(app, pumpar):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        assert request.headers["authorization"] == "Bearer tok"
        assert json.loads(request.read())["chave_ativacao"] == _CHAVE
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler)
    emitiu = []
    janela.ativada.connect(lambda: emitiu.append(True))

    janela._campo_chave.setText(_CHAVE)
    janela._ativar()

    pumpar(lambda: janela._cartao.currentIndex() == 1)
    assert "/v1/licenca/ativar" in chamadas
    assert "Licença ativada" in janela._sucesso_titulo.text()
    assert "ANUAL" in janela._sucesso_resumo.text()
    assert "19/10/2027" in janela._sucesso_resumo.text()
    assert janela._passo == 3
    assert janela._botao_ativar.isEnabled()  # validação encerrou

    # `ativada` só dispara no "Entrar" (D1) — não no retorno da API.
    assert emitiu == []
    janela._botao_entrar.click()
    assert emitiu == [True]


def test_erro_do_servidor_e_exibido_junto_dos_campos(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"detail": "Chave de ativação não reconhecida pelo servidor."}
        )

    janela = _janela(handler)
    janela._campo_chave.setText(_CHAVE)
    janela._ativar()

    pumpar(lambda: "não reconhecida" in janela._erro.text())
    assert not janela._linha_validando.isVisible()
    assert janela._passo == 1  # voltou ao passo de dados


def test_erro_nao_trava_o_botao(app, pumpar):
    janela = _janela(lambda r: httpx.Response(400, json={"detail": "Chave inválida."}))
    janela._campo_chave.setText(_CHAVE)
    janela._ativar()
    pumpar(lambda: janela._erro.text() != "")
    assert janela._botao_ativar.isEnabled()
    assert janela._campo_chave.isEnabled()


def test_erro_do_servidor_foca_o_campo_relacionado(app, pumpar):
    janela = _janela(
        lambda r: httpx.Response(400, json={"detail": "CNPJ não corresponde ao titular."}),
        contrato="b",
    )
    janela._campo_cnpj.setText(_CNPJ_VALIDO)
    janela._campo_codigo.setText("COD-123")
    janela._ativar()
    pumpar(lambda: janela._erro.text() != "")
    # O foco vai para o campo relacionado à mensagem (C6).
    assert janela._campo_do_erro("CNPJ não corresponde") is janela._campo_cnpj
    assert janela._campo_do_erro("o código informado é inválido") is janela._campo_codigo
    assert janela._campo_do_erro("Servidor de licenças indisponível.") is None


# ------------------------------------------------------- CNPJ (D4, Contrato B)


def test_cnpj_formatado_ao_digitar(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela._campo_cnpj.setText("11222333000181")
    assert janela._campo_cnpj.text() == _CNPJ_VALIDO


def test_cnpj_com_digito_invalido_e_rejeitado_em_linha(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela._campo_cnpj.setText("11222333000182")  # dígito verificador errado
    janela._campo_cnpj.editingFinished.emit()
    assert "CNPJ inválido" in janela._erro_cnpj.text()
    assert janela._campo_cnpj.property("estado") == "erro"


def test_cnpj_valido_passa_pela_validacao(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela._campo_cnpj.setText(_CNPJ_VALIDO)
    assert janela._validar_cnpj() is True


def test_cnpj_vazio_ao_sair_do_campo_nao_grita(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela._campo_cnpj.editingFinished.emit()
    assert janela._erro_cnpj.isHidden()  # vazio no blur: silencioso (D4)


def test_codigo_sem_espacos_e_validado_ao_enviar(app):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(json.loads(request.read()))
        return httpx.Response(200, json={"data": _RESPOSTA_ATIVA})

    janela = _janela(handler, contrato="b")
    janela._campo_cnpj.setText(_CNPJ_VALIDO)
    janela._campo_codigo.setText("  ABC 123  ")
    janela._ativar()
    assert chamadas and chamadas[-1]["codigo_licenca"] == "ABC123"
    assert chamadas[-1]["cnpj"] == "11222333000181"


def test_codigo_vazio_pede_o_campo(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela._campo_cnpj.setText(_CNPJ_VALIDO)
    janela._ativar()
    assert "Informe o código" in janela._erro_codigo.text()


# ------------------------------------------------------------ validação (D2)


def test_validando_mostra_barra_e_cancelar_devolve_o_formulario(app):
    """Estados da espera (D2): barra visível, campos travados; Cancelar devolve.

    Limitação documentada: o pedido HTTP não é abortável — o resultado, quando
    chega, ainda é aplicado (ver `_cancelar_validacao`).
    """
    janela = _janela(lambda r: httpx.Response(200, json={"data": _RESPOSTA_ATIVA}))
    janela._campo_chave.setText(_CHAVE)
    janela._entrar_em_validacao()

    assert not janela._linha_validando.isHidden()
    assert not janela._campo_chave.isEnabled()
    assert janela._botao_ativar.text() == "Validando…"

    janela._cancelar_validacao()
    assert janela._linha_validando.isHidden()
    assert janela._botao_ativar.isEnabled()
    assert janela._botao_ativar.text() == "Ativar licença (F10)"
    assert janela._campo_chave.isEnabled()


def test_resultado_apos_cancelar_ainda_e_aplicado(app, pumpar):
    """Cancelada a espera, a licença ativada entra assim mesmo (fato consumado)."""
    janela = _janela(lambda r: httpx.Response(200, json={"data": _RESPOSTA_ATIVA}))
    janela._campo_chave.setText(_CHAVE)
    janela._entrar_em_validacao()
    janela._cancelar_validacao()
    janela._cancelado is True
    janela._disparar(lambda: dict(_RESPOSTA_ATIVA))
    pumpar(lambda: janela._cartao.currentIndex() == 1)
    assert "Licença ativada" in janela._sucesso_titulo.text()


# ------------------------------------------------------ conexão local (D3)


def test_status_do_servidor_local_automatico_e_honesto(app, pumpar):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    pumpar(lambda: "conectado" in janela._status.text())


def test_status_sem_daemon(app, pumpar):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("daemon fora do ar")

    janela = _janela(handler)
    pumpar(lambda: "sem resposta" in janela._status.text())


def test_botao_tentar_novamente_reativa_o_diagnostico(app, pumpar):
    chamadas = []

    def handler(request: httpx.Request) -> httpx.Response:
        chamadas.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    janela = _janela(handler)
    pumpar(lambda: len(chamadas) >= 1)
    janela._botao_tentar.click()
    pumpar(lambda: len(chamadas) >= 2)
    assert all(c == "/health" for c in chamadas)


# ---------------------------------------------------------------- saída (D5)


def test_esc_e_saida_pedem_confirmacao(app, monkeypatch):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    chamadas = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: chamadas.append(1) or QMessageBox.StandardButton.Yes,
    )
    emitido = []
    janela.saida.connect(lambda: emitido.append(True))
    janela._solicitar_saida()
    assert chamadas == [1]
    assert emitido == [True]


def test_cancelar_a_saida_nao_emite(app, monkeypatch):
    janela = _janela(lambda r: httpx.Response(200, json={"status": "ok"}))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.No,
    )
    emitido = []
    janela.saida.connect(lambda: emitido.append(True))
    janela._solicitar_saida()
    assert emitido == []


# ------------------------------------------------- textos e contrato (C1–C4)


def test_textos_da_superficie_sem_jargao(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    textos = " ".join(
        w.text() for w in janela.findChildren(type(janela._status))
    ).lower()
    for proibido in ("redgest", "contrato b", "local api service", "host principal"):
        assert proibido not in textos, f"jargão na superfície: {proibido}"


def test_contrato_b_usa_cnpj_e_codigo(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    assert "CNPJ da empresa" in janela._campo_cnpj.accessibleName()
    assert "Passo 1 de 3 · Dados da licença" in janela._passo_texto.text()


def test_contrato_c_usa_chave_de_produto(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="c")
    assert "Chave de produto" in janela._campo_chave.accessibleName()
    assert "Passo 1 de 3 · Chave de produto" in janela._passo_texto.text()


def test_campos_tem_nome_acessivel_e_placeholder_legivel(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    assert janela._campo_cnpj.accessibleName() == "CNPJ da empresa"
    assert janela._campo_cnpj.placeholderText() == "00.000.000/0000-00"


# ----------------------------------------------------------- layout (A2/B)


def test_sem_altura_fixa_que_corte_texto(app):
    """Ajuda e rótulos renderizam com a altura que o texto pede (A2)."""
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela.resize(1280, 720)
    app.processEvents()
    for lbl in janela.centralWidget().findChildren(type(janela._status)):
        if not lbl.wordWrap() or lbl.isHidden():
            continue
        necessaria = lbl.heightForWidth(lbl.width())
        if necessaria > 0:
            assert lbl.height() >= necessaria, f"texto cortado: {lbl.text()!r}"


def test_cabeca_e_rodape_cabem_em_1280x720(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    janela.resize(1280, 720)
    janela.show()
    app.processEvents()
    central = janela.centralWidget()
    assert central.sizeHint().height() <= 720, (
        "coluna não cabe em 720 px de altura",
        central.sizeHint(),
    )
    assert janela._cartao.maximumWidth() == 560


def test_campos_do_contrato_b_estao_na_ordem_de_tab(app):
    janela = _janela(lambda r: httpx.Response(200), contrato="b")
    foco = janela._campo_cnpj.nextInFocusChain()
    ordem = []
    atual = janela._campo_cnpj
    for _ in range(30):
        ordem.append(atual)
        atual = atual.nextInFocusChain()
        if atual is janela._campo_cnpj:
            break
    assert janela._campo_codigo in ordem
    assert ordem.index(janela._campo_cnpj) < ordem.index(janela._campo_codigo)
