"""Módulo Financeiro (PRD v2.1 §1.5 / telas_e_fluxos §1.5, §2.4).

Quatro telas sob o menu "Financeiro", reunidas num host com sub-abas:

- **Caixa** — abertura, extrato do dia (movimentos) e fechamento com conferência.
- **Contas a Receber** — lista + baixa de pagamento (nascem das O.S./vendas).
- **Contas a Pagar** — lista + baixa de pagamento (nascem dos pedidos de compra).
- **Plano de Contas** — cadastro (CRUD genérico).

Perfil `caixa` enxerga apenas a aba **Caixa**; contas e plano de contas exigem
GERENTE+ (mesma regra do RBAC do menu — `core/rbac.py`).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from printgest.core.rbac import tem_acesso
import printgest.core.tarefas as tarefas
from printgest.ui import animacao
from printgest.ui.formulario import (
    CampoArea,
    CampoCheck,
    CampoCombo,
    CampoData,
    CampoTexto,
    CampoValor,
    data_iso,
    em_volta,
    formatar_data_hora,
    formatar_data_iso,
    formatar_moeda,
    limpo,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.paginador import LOTE, Paginador
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import ElideLabel, badge, botao_com_atalho

_STATUS_CONTA = {
    "aberta": "ABERTA",
    "paga": "PAGA",
    "cancelada": "CANCELADA",
}
_TIPOS_MOV = [
    ("suprimento", "Suprimento (entrada)"),
    ("sangria", "Sangria (saída)"),
]
_MOV_SAIDA = ("saida", "sangria")


def _dt(valor) -> str:
    """Data/hora ISO → 'DD/MM/AAAA HH:MM' (helper compartilhado)."""
    return formatar_data_hora(valor)


def _valor_movimento(mov: dict) -> str:
    sinal = "-" if mov.get("tipo") in _MOV_SAIDA else "+"
    return f"{sinal} {formatar_moeda(mov.get('valor'))}"


# ================================================================ caixa


class PaginaCaixa(QWidget):
    """1.5 — Caixa: Abertura / Extrato do Dia / Fechamento (fluxo §2.4)."""

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._caixa: dict | None = None
        self._caixa_id_extrato: int | None = None
        self._fechado: dict | None = None
        self._seq = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._barra_titulo())
        layout.addWidget(self._corpo(), 1)
        self._instalar_atalhos()
        self._aplicar_estado()
        self.recarregar()

    # ----------------------------------------------------------- construção

    def _barra_titulo(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        titulo = ElideLabel("Caixa — Abertura / Extrato / Fechamento")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo, 1)
        self._badge_status = badge("SEM CAIXA", "atencao")
        self._badge_saldo = badge("Saldo: –", "primary")
        linha.addWidget(self._badge_status)
        linha.addWidget(self._badge_saldo)
        return caixa

    def _corpo(self) -> QWidget:
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)

        esquerda = QWidget()
        esquerda.setObjectName("card")
        col = QVBoxLayout(esquerda)
        col.setContentsMargins(0, 8, 0, 0)
        col.setSpacing(0)
        self._tabela = TabelaDensa(
            ["criado_em", "tipo", "descricao", "valor"],
            ["Data/Hora", "Tipo", "Descrição", "Valor"],
            [3, 2, 6, 3],
        )
        self._tabela.formata = self._formatar_mov
        col.addWidget(self._tabela, 1)
        self._paginador = Paginador()
        self._paginador.mudou.connect(self._carregar_extrato)
        pag = QWidget()
        pag_l = QHBoxLayout(pag)
        pag_l.setContentsMargins(14, 8, 14, 8)
        pag_l.addWidget(self._paginador)
        col.addWidget(pag)
        divisor.addWidget(esquerda)

        divisor.addWidget(self._painel())
        divisor.setStretchFactor(0, 1)
        divisor.setStretchFactor(1, 0)
        divisor.setSizes([720, 360])
        return divisor

    def _painel(self) -> QWidget:
        painel = QWidget()
        painel.setObjectName("card")
        painel.setMinimumWidth(320)
        col = QVBoxLayout(painel)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(12)

        self._titulo_painel = ElideLabel("Abertura de Caixa")
        self._titulo_painel.setObjectName("titulo")
        col.addWidget(self._titulo_painel)

        # --- Abertura
        self._painel_abertura = QWidget()
        pa = QVBoxLayout(self._painel_abertura)
        pa.setContentsMargins(0, 0, 0, 0)
        pa.setSpacing(10)
        self._f_abertura = CampoValor("Valor de Abertura")
        self._f_abertura.definir("0")
        self._f_obs_abertura = CampoArea("Observações", linhas=2)
        pa.addWidget(em_volta(self._f_abertura))
        pa.addWidget(em_volta(self._f_obs_abertura))
        abrir, self._btn_abrir = botao_com_atalho("Abrir Caixa", "F6", "primary")
        self._btn_abrir.clicked.connect(self._abrir)
        pa.addWidget(abrir)
        pa.addStretch(1)
        col.addWidget(self._painel_abertura)

        # --- Movimento (caixa aberto)
        self._painel_movimento = QWidget()
        pm = QVBoxLayout(self._painel_movimento)
        pm.setContentsMargins(0, 0, 0, 0)
        pm.setSpacing(10)
        self._f_tipo = CampoCombo("Tipo de Lançamento", _TIPOS_MOV)
        self._f_valor = CampoValor("Valor")
        self._f_desc = CampoTexto("Descrição")
        pm.addWidget(em_volta(self._f_tipo))
        pm.addWidget(em_volta(self._f_valor))
        pm.addWidget(em_volta(self._f_desc))
        lancar, self._btn_lancar = botao_com_atalho("Lançar Movimento", "F7")
        self._btn_lancar.clicked.connect(self._lancar)
        pm.addWidget(lancar)
        pm.addStretch(1)
        col.addWidget(self._painel_movimento)

        # --- Fechamento (caixa aberto)
        self._painel_fechamento = QWidget()
        pf = QVBoxLayout(self._painel_fechamento)
        pf.setContentsMargins(0, 0, 0, 0)
        pf.setSpacing(10)
        self._f_informado = CampoValor("Valor Informado (conferência física)")
        self._f_obs_fech = CampoArea("Observações", linhas=2)
        pf.addWidget(em_volta(self._f_informado))
        pf.addWidget(em_volta(self._f_obs_fech))
        fechar, self._btn_fechar = botao_com_atalho("Fechar Caixa", "F9", "primary")
        self._btn_fechar.clicked.connect(self._fechar)
        pf.addWidget(fechar)
        pf.addStretch(1)
        col.addWidget(self._painel_fechamento)

        # --- Informação (caixa fechado / sem caixa)
        self._info = QLabel("")
        self._info.setObjectName("subtitulo")
        self._info.setWordWrap(True)
        col.addWidget(self._info)
        col.addStretch(1)
        self._painel_dir = painel
        return painel

    def _instalar_atalhos(self) -> None:
        QShortcut(QKeySequence("F6"), self, self._abrir)
        QShortcut(QKeySequence("F7"), self, self._lancar)
        QShortcut(QKeySequence("F9"), self, self._fechar)

    # ---------------------------------------------------------------- estado

    def recarregar(self, *_args) -> None:
        self._seq += 1
        seq = self._seq

        def _receber(caixa) -> None:
            if seq != self._seq:
                return
            self._caixa = caixa if isinstance(caixa, dict) else None
            if self._caixa:
                self._caixa_id_extrato = self._caixa["id"]
            self._aplicar_estado()
            self._carregar_extrato()

        tarefas.rodar(
            lambda: self._api.caixa_atual(),
            on_ok=_receber,
            on_erro=lambda msg: QMessageBox.warning(self, "Caixa", msg),
        )

    def _aplicar_estado(self) -> None:
        aberto = self._caixa is not None
        self._painel_abertura.setVisible(not aberto)
        self._painel_movimento.setVisible(aberto)
        self._painel_fechamento.setVisible(aberto)
        self._titulo_painel.setText(
            "Abertura de Caixa" if not aberto else "Movimento & Fechamento"
        )
        # Estado vazio do extrato coerente com o status (não pedir para abrir
        # o caixa quando ele já está aberto — achado da revisão de telas).
        self._tabela.estado_vazio(
            "Sem movimentos - abra o caixa à direita (F6)."
            if not aberto
            else "Nenhum movimento registrado neste caixa ainda."
        )

        if aberto:
            self._badge_status.setText("CAIXA ABERTO")
            self._badge_status.setProperty("badgeStyle", "primary")
            self._badge_saldo.setText(
                f"Saldo: {formatar_moeda(self._caixa.get('saldo_atual'))}"
            )
            self._info.setText(
                "Cada venda balcão/recebimento gera lançamento automático. Use "
                "sangria/suprimento para ajustes manuais e feche o caixa ao fim do "
                "expediente (o valor esperado é conferido com o informado)."
            )
        else:
            self._badge_status.setText("SEM CAIXA")
            self._badge_status.setProperty("badgeStyle", "atencao")
            self._badge_saldo.setText("Saldo: –")
            self._info.setText(
                "Nenhum caixa aberto para este usuário. Informe o valor inicial e "
                "pressione Abrir Caixa (F6)."
            )
        for badge_ in (self._badge_status, self._badge_saldo):
            badge_.style().unpolish(badge_)
            badge_.style().polish(badge_)

        if self._modo_leitura:
            for botao in (self._btn_abrir, self._btn_lancar, self._btn_fechar):
                botao.setEnabled(False)

    # ---------------------------------------------------------------- extrato

    def _carregar_extrato(self, offset: int = 0) -> None:
        caixa_id = self._caixa_id_extrato
        if not caixa_id:
            self._tabela.limpar()
            self._paginador.atualizar(0, 0, LOTE)
            return
        tarefas.rodar(
            lambda: self._api.extrato_caixa(caixa_id, limit=LOTE, offset=offset),
            on_ok=lambda saida: self._extrato_recebido(saida, offset),
            on_erro=lambda msg: QMessageBox.warning(self, "Extrato do Caixa", msg),
        )

    def _extrato_recebido(self, saida: dict, offset: int = 0) -> None:
        self._tabela.preencher(saida.get("data", []))
        self._paginador.atualizar(saida.get("total", 0), offset, LOTE)

    def _formatar_mov(self, dado: dict, chave: str) -> str:
        if chave == "criado_em":
            return _dt(dado.get(chave))
        if chave == "tipo":
            return str(dado.get(chave, "")).upper()
        if chave == "valor":
            return _valor_movimento(dado)
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

    # ---------------------------------------------------------------- ações

    def _abrir(self) -> None:
        if self._caixa is not None or self._modo_leitura:
            return
        payload = {
            "valor_abertura": str(self._f_abertura.valor() or "0"),
            "observacoes": limpo(self._f_obs_abertura.valor()),
        }
        self._btn_abrir.setEnabled(False)
        tarefas.rodar(
            lambda: self._api.abrir_caixa(payload),
            on_ok=lambda _c: self._acao_ok(),
            on_erro=self._erro,
        )

    def _lancar(self) -> None:
        if self._caixa is None or self._modo_leitura:
            return
        valor = self._f_valor.valor()
        if not valor or valor <= 0:
            QMessageBox.warning(self, "Caixa", "Informe um valor maior que zero.")
            self._f_valor.widget.setFocus()
            return
        payload = {
            "tipo": self._f_tipo.valor(),
            "valor": str(valor),
            "descricao": limpo(self._f_desc.valor()),
        }
        caixa_id = self._caixa["id"]
        self._btn_lancar.setEnabled(False)
        tarefas.rodar(
            lambda: self._api.movimento_caixa(caixa_id, payload),
            on_ok=lambda _m: self._acao_ok(),
            on_erro=self._erro,
        )

    def _fechar(self) -> None:
        if self._caixa is None or self._modo_leitura:
            return
        informado = self._f_informado.valor()
        if informado is None:
            QMessageBox.warning(self, "Caixa", "Informe o valor conferido.")
            self._f_informado.widget.setFocus()
            return
        caixa_id = self._caixa["id"]
        esperado = Decimal(str(self._caixa.get("saldo_atual") or "0"))
        diferenca = informado - esperado
        if diferenca != 0:
            resposta = QMessageBox.question(
                self,
                "Fechar caixa",
                f"Há divergência de {formatar_moeda(diferenca)}.\nConfirmar o "
                "fechamento mesmo assim?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        payload = {
            "valor_informado": str(informado),
            "observacoes": limpo(self._f_obs_fech.valor()),
        }
        self._btn_fechar.setEnabled(False)
        tarefas.rodar(
            lambda: self._api.fechar_caixa(caixa_id, payload),
            on_ok=self._fechado_ok,
            on_erro=self._erro,
        )

    def _acao_ok(self) -> None:
        self._f_valor.definir(None)
        self._f_desc.definir(None)
        self.recarregar()

    def _fechado_ok(self, caixa: dict) -> None:
        self._caixa = None
        self._caixa_id_extrato = caixa.get("id")
        self._aplicar_estado()
        diferenca = caixa.get("diferenca")
        if diferenca not in (None, "", "0", "0.00"):
            texto = formatar_moeda(diferenca)
        else:
            texto = "sem divergência"
        QMessageBox.information(
            self, "Caixa fechado", f"Caixa fechado — conferência: {texto}."
        )
        self.recarregar()

    def _erro(self, msg: str) -> None:
        for botao in (self._btn_abrir, self._btn_lancar, self._btn_fechar):
            botao.setEnabled(not self._modo_leitura)
        QMessageBox.critical(self, "Caixa", msg)


# ================================================================ contas


def _dialogo_baixa(parent, conta: dict, titulo: str) -> dict | None:
    """Pede valor/data da baixa; retorna o payload ou `None` se cancelado."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(titulo)
    col = QVBoxLayout(dialog)
    col.setContentsMargins(16, 16, 16, 16)
    col.setSpacing(10)

    saldo = Decimal(str(conta.get("valor") or "0")) - Decimal(
        str(conta.get("valor_pago") or "0")
    )
    campo_valor = CampoValor("Valor da Baixa")
    campo_valor.definir(str(saldo))
    campo_data = CampoData("Data do Pagamento", aceita_sem_data=False)
    campo_data.definir(date.today())
    campo_obs = CampoArea("Observações", linhas=2)
    for campo in (campo_valor, campo_data, campo_obs):
        col.addWidget(em_volta(campo))

    rodape = QHBoxLayout()
    rodape.addStretch(1)
    cancelar, btn_cancelar = botao_com_atalho("Cancelar", "Esc")
    confirmar, btn_confirmar = botao_com_atalho("Confirmar Baixa", "", "primary")
    btn_cancelar.clicked.connect(dialog.reject)
    btn_confirmar.clicked.connect(dialog.accept)
    rodape.addWidget(cancelar)
    rodape.addWidget(confirmar)
    col.addLayout(rodape)

    animacao.revelar_janela(dialog)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    valor = campo_valor.valor()
    if not valor or valor <= 0:
        return None
    return {
        "valor_pago": str(valor),
        "data_pagamento": data_iso(campo_data.valor()),
        "observacoes": limpo(campo_obs.valor()),
    }


class PaginaContas(PaginaCrud):
    """Lista de títulos + baixa de pagamento. Somente consulta + ação de baixa."""

    ROTULO_EXPORTAR = "Exportar Excel"
    GRUPO_LISTA = "TÍTULOS"
    CHAVE_FILTRO = "status_conta"
    FILTROS = [
        ("", "Todas"),
        ("aberta", "Abertas"),
        ("paga", "Pagas"),
        ("cancelada", "Canceladas"),
    ]
    CAMPO_NOME = "descricao"

    TIPO_API = "contas-receber"
    TITULO_BAIXA = "Dar Baixa"
    NOME_PARTE = "Cliente"

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)

    # ------------------------------------------------------------- formulário

    def _secoes(self):
        self._f_desc = CampoTexto("Descrição")
        self._f_parte = CampoTexto(self.NOME_PARTE)
        self._f_plano = CampoTexto("Plano de Conta")
        self._f_venc = CampoTexto("Vencimento")
        self._f_valor = CampoValor("Valor")
        self._f_pago = CampoValor("Valor Pago")
        self._f_status = CampoTexto("Status")
        self._f_data_pg = CampoTexto("Data do Pagamento")
        self._f_obs = CampoArea("Observações", linhas=2)
        return [
            ("Título", [self._f_desc, self._f_parte, self._f_plano, self._f_venc]),
            ("Valores", [self._f_valor, self._f_pago, self._f_status, self._f_data_pg]),
            ("Complementos", [self._f_obs]),
        ]

    def _preencher_campos(self, dado: dict) -> None:
        self._f_desc.definir(dado.get("descricao"))
        self._f_parte.definir(dado.get("cliente_nome") or dado.get("fornecedor_nome") or "—")
        plano = dado.get("plano_conta_id")
        self._f_plano.definir(f"#{plano}" if plano else "—")
        self._f_venc.definir(formatar_data_iso(dado.get("vencimento")))
        self._f_valor.definir(dado.get("valor"))
        self._f_pago.definir(dado.get("valor_pago"))
        self._f_status.definir(
            _STATUS_CONTA.get(dado.get("status"), dado.get("status") or "")
        )
        self._f_data_pg.definir(formatar_data_iso(dado.get("data_pagamento")) or "—")
        self._f_obs.definir(dado.get("observacoes"))

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave in ("valor", "valor_pago"):
            return formatar_moeda(dado.get(chave))
        if chave in ("vencimento", "data_pagamento"):
            return formatar_data_iso(dado.get(chave))
        if chave == "status":
            return _STATUS_CONTA.get(dado.get(chave), str(dado.get(chave) or ""))
        return super()._formatar_texto(dado, chave)

    # ------------------------------------------------------------- atalhos/leitura

    def _instalar_atalhos(self) -> None:
        # Tela de consulta: só a ação de baixa tem atalho (F9).
        QShortcut(QKeySequence("F9"), self, self._dar_baixa)

    def _aplicar_modo_leitura_acoes(self) -> None:
        super()._aplicar_modo_leitura_acoes()
        # Campos e ações de CRUD nunca são usados: a tela é lista + baixa.
        for campo in self._campos():
            campo.habilitar(False)
        for botao in (self._btn_novo, self._btn_salvar, self._btn_cancelar):
            botao.setEnabled(False)
        for extra in getattr(self, "_acoes_extra", []):
            extra.setEnabled(not self._modo_leitura)
            for botao in extra.findChildren(QPushButton):
                botao.setEnabled(not self._modo_leitura)

    # ---------------------------------------------------------------- baixa

    def _acao_extra(self):
        baixa, self._btn_baixa = botao_com_atalho(self.TITULO_BAIXA, "F9", "primary")
        self._btn_baixa.clicked.connect(self._dar_baixa)
        return [baixa]

    def _dar_baixa(self) -> None:
        if self._modo_leitura:
            return
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(
                self, self.ROTULO_PAGINA, "Selecione um título na lista."
            )
            return
        if dado.get("status") != "aberta":
            QMessageBox.information(
                self, self.ROTULO_PAGINA, "Somente títulos em aberto recebem baixa."
            )
            return
        payload = _dialogo_baixa(self, dado, self.TITULO_BAIXA)
        if payload is None:
            return
        conta_id = dado["id"]
        self._btn_baixa.setEnabled(False)
        tarefas.rodar(
            lambda: self._api.baixa_conta(self.TIPO_API, conta_id, payload),
            on_ok=self._baixa_ok,
            on_erro=self._baixa_erro,
        )

    def _baixa_ok(self, _dado: dict) -> None:
        self._btn_baixa.setEnabled(True)
        self.recarregar(self._busca.texto())

    def _baixa_erro(self, msg: str) -> None:
        self._btn_baixa.setEnabled(True)
        QMessageBox.critical(self, self.ROTULO_PAGINA, msg)


class PaginaContasReceber(PaginaContas):
    ENTIDADE = "financeiro/contas-receber"
    ROTULO_PAGINA = "Contas a Receber"
    ROTULO_NOVO = "Novo Recebimento"
    GRUPO_LISTA = "TÍTULOS A RECEBER"
    LUGAR_BUSCA = "Buscar por descrição ou cliente..."
    TIPO_API = "contas-receber"
    TITULO_BAIXA = "Receber"
    NOME_PARTE = "Cliente"
    CHAVES = ["id", "descricao", "cliente_nome", "vencimento", "valor", "valor_pago", "status"]
    COLUNAS = ["Nº", "Descrição", "Cliente", "Vencimento", "Valor", "Pago", "Status"]
    PESOS = [1, 5, 4, 2, 2, 2, 2]


class PaginaContasPagar(PaginaContas):
    ENTIDADE = "financeiro/contas-pagar"
    ROTULO_PAGINA = "Contas a Pagar"
    ROTULO_NOVO = "Novo Pagamento"
    GRUPO_LISTA = "TÍTULOS A PAGAR"
    LUGAR_BUSCA = "Buscar por descrição ou fornecedor..."
    TIPO_API = "contas-pagar"
    TITULO_BAIXA = "Pagar"
    NOME_PARTE = "Fornecedor"
    CHAVES = ["id", "descricao", "fornecedor_nome", "vencimento", "valor", "valor_pago", "status"]
    COLUNAS = ["Nº", "Descrição", "Fornecedor", "Vencimento", "Valor", "Pago", "Status"]
    PESOS = [1, 5, 4, 2, 2, 2, 2]


# ================================================================ plano de contas


class PaginaPlanoContas(PaginaCrud):
    ENTIDADE = "plano-contas"
    ROTULO_PAGINA = "Plano de Contas"
    ROTULO_NOVO = "Nova Conta"
    GRUPO_LISTA = "PLANO DE CONTAS"
    LUGAR_BUSCA = "Buscar por código ou nome..."
    CAMPO_NOME = "nome"
    CHAVES = ["codigo", "nome", "tipo", "ativo"]
    COLUNAS = ["Código", "Nome", "Tipo", "Ativo"]
    PESOS = [2, 6, 2, 1]
    CHAVE_FILTRO = "tipo"
    FILTROS = [("", "Todas"), ("receita", "Receitas"), ("despesa", "Despesas")]

    def _secoes(self):
        self._f_codigo = CampoTexto("Código", maximo=20).obrigatorio()
        self._f_nome = CampoTexto("Nome").obrigatorio()
        self._f_tipo = CampoCombo(
            "Tipo", [("receita", "Receita"), ("despesa", "Despesa")]
        ).obrigatorio()
        self._f_ativo = CampoCheck("Ativo")
        return [("Conta", [self._f_codigo, self._f_nome, self._f_tipo, self._f_ativo])]

    def _padroes_do_form(self) -> None:
        self._f_ativo.definir(True)

    def _preencher_campos(self, dado: dict) -> None:
        self._f_codigo.definir(dado.get("codigo"))
        self._f_nome.definir(dado.get("nome"))
        self._f_tipo.definir(dado.get("tipo"))
        self._f_ativo.definir(dado.get("ativo", True))

    def _payload(self) -> dict:
        return {
            "codigo": self._f_codigo.valor(),
            "nome": self._f_nome.valor(),
            "tipo": self._f_tipo.valor(),
            "ativo": self._f_ativo.valor(),
        }

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "tipo":
            return str(dado.get(chave, "")).capitalize()
        if chave == "ativo":
            return "Sim" if dado.get(chave) else "Não"
        return super()._formatar_texto(dado, chave)


# ================================================================ host


class PaginaFinanceiro(QWidget):
    """Menu "Financeiro": hospeda as sub-abas conforme o perfil do usuário."""

    def __init__(self, api, modo_leitura: bool = False, nivel: str | None = None) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._abas = [("Caixa", PaginaCaixa)]
        if nivel is None or tem_acesso(nivel, "gerente"):
            self._abas += [
                ("Contas a Receber", PaginaContasReceber),
                ("Contas a Pagar", PaginaContasPagar),
                ("Plano de Contas", PaginaPlanoContas),
            ]
        self._atual: QWidget | None = None

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._barra())
        self._corpo = QWidget()
        self._corpo_layout = QVBoxLayout(self._corpo)
        self._corpo_layout.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self._corpo, 1)
        self._trocar(0)

    def _barra(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 16, 20, 0)
        linha.setSpacing(8)
        titulo = ElideLabel("Financeiro")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo)
        linha.addStretch(1)
        self._botoes = []
        for indice, (rotulo, _classe) in enumerate(self._abas):
            botao = QPushButton(rotulo)
            botao.setObjectName("chaveRapida")
            botao.setCheckable(True)
            botao.setChecked(indice == 0)
            botao.clicked.connect(lambda _=False, i=indice: self._trocar(i))
            self._botoes.append(botao)
            linha.addWidget(botao)
        return caixa

    def _trocar(self, indice: int) -> None:
        _rotulo, classe = self._abas[indice]
        pagina = classe(self._api, modo_leitura=self._modo_leitura)
        if self._atual is not None:
            self._corpo_layout.removeWidget(self._atual)
            self._atual.deleteLater()
        self._corpo_layout.addWidget(pagina)
        self._atual = pagina
        for i, botao in enumerate(self._botoes):
            botao.setChecked(i == indice)
