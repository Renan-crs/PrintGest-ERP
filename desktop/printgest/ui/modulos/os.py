"""Módulo Movimento — Ordem de Serviço (mockup 3.1/3.2) e Orçamentos (3.3).

Ordem de serviço e orçamento vivem na mesma rota `/v1/os`, diferenciados por
`tipo`. A página é a mesma base `PaginaCrud` com `TIPO` fixo; a subclasse de
orçamento troca rótulos e adiciona a ação de conversão (`POST /{id}/converter`).
O avanço de status usa `PATCH /{id}/status` e o cancelamento `DELETE /{id}`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QFileDialog,
    QInputDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.dominio import FORMAS_PAGAMENTO
from printgest.core.dominio.ordem_servico import (
    _PROXIMO_STATUS,
    _rotulo_status,
)
import printgest.core.tarefas as tarefas
from printgest.ui.formulario import (
    CampoArea,
    CampoCheck,
    CampoClienteAutocomplete,
    CampoCombo,
    CampoData,
    CampoDataHora,
    CampoTexto,
    CampoValor,
    data_iso,
    em_volta,
    formatar_data_iso,
    formatar_moeda,
    limpo,
    para_decimal,
)
from printgest.ui.grade_itens import GradeItens
from printgest.ui.modulos.condicao_pagamento import CondicaoPagamentoCliente
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.paginador import LOTE
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import (
    aplicar_estilo,
    botao_com_atalho,
    estado_sucesso,
    estado_erro,
    estado_muted,
    estado_atencao,
    estado_primario,
    estado_danger,
    formatar_datahora,
)


class _MenuAcima(QToolButton):
    """Menu do rodapé: abre acima e alinhado à direita do botão."""

    def showMenu(self) -> None:  # noqa: N802 - API do Qt
        menu = self.menu()
        if menu is None:
            return
        origem = self.mapToGlobal(QPoint(0, 0))
        largura = max(menu.sizeHint().width(), self.width())
        menu.popup(
            QPoint(
                origem.x() + self.width() - largura,
                origem.y() - menu.sizeHint().height(),
            )
        )


# ------------------------------------------------------- diálogo de cotações

_COTACAO_CHAVES = ["fornecedor_nome", "vf", "prazo_dias", "validade", "selecionada"]
_COTACAO_ROTULOS = [
    "Fornecedor", "Valor fornecedor", "Prazo (dias)", "Validade", "Selecionada"
]


class DialogoCotacoes(QDialog):
    """Comparativo enxuto: uma linha por fornecedor, VF editável, rádio de aprovação.

    O usuário digita o VF de cada opção na própria tabela e escolhe a melhor
    oferta pelo rádio. O backend calcula CP/VO ao aprovar; o snapshot volta em
    `aprovado` para a grade atualizar VF/CP/Preço Unitário sem recarregar a tela.
    """

    _COLunas = ["fornecedor", "vf", "prazo", "validade", "selecionar"]

    def __init__(self, parent, api, os_id: int, item: dict) -> None:
        super().__init__(parent)
        self._api = api
        self._os_id = os_id
        self._item = item
        self._cotacoes: list[dict] = []
        self._fornecedores: list[tuple[int, str]] = []
        self._preenchendo = False
        self.aprovado: dict | None = None

        descricao = item.get("descricao_avulsa") or "item selecionado"
        dimensoes = item.get("dimensoes")
        titulo = f"Cotação do Item: {descricao}"
        if dimensoes:
            titulo += f" ({dimensoes})"

        self.setWindowTitle("Cotações de Fornecedor")
        self.setMinimumSize(760, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        cabecalho = QLabel(titulo)
        cabecalho.setObjectName("titulo")
        root.addWidget(cabecalho)

        self._lbl_estado = QLabel("Carregando…")
        estado_muted(self._lbl_estado)
        root.addWidget(self._lbl_estado)

        self._tabela = TabelaDensa(
            self._COLunas,
            ["Fornecedor", "VF (R$)", "Prazo (dias)", "Validade", "Selecionar"],
        )
        self._tabela.setMinimumHeight(180)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._tabela.itemChanged.connect(self._celula_alterada)
        self._tabela.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self._tabela, 1)

        self._lbl_calculo = QLabel(
            "O sistema calcula CP (VF × 2,30) e Preço Unitário (CP × 1,06) "
            "automaticamente a partir do VF aprovado."
        )
        self._lbl_calculo.setWordWrap(True)
        estado_muted(self._lbl_calculo)
        root.addWidget(self._lbl_calculo)

        self._lbl_snapshot = QLabel("")
        self._lbl_snapshot.setWordWrap(True)
        estado_muted(self._lbl_snapshot)
        root.addWidget(self._lbl_snapshot)

        linha = QHBoxLayout()
        self._btn_adicionar = QPushButton("+ Adicionar Fornecedor Manual")
        self._btn_adicionar.clicked.connect(self._adicionar_linha)
        linha.addWidget(self._btn_adicionar)
        linha.addStretch(1)
        root.addLayout(linha)

        botoes = QHBoxLayout()
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        self._btn_aprovar = QPushButton("Aprovar Cotação")
        estado_primario(self._btn_aprovar)
        self._btn_aprovar.clicked.connect(self._aprovar)
        botoes.addStretch(1)
        botoes.addWidget(cancelar)
        botoes.addWidget(self._btn_aprovar)
        root.addLayout(botoes)

        self._carregar_fornecedores()
        self._carregar()

    # ------------------------------------------------------------- dados

    def _carregar_fornecedores(self) -> None:
        catalogos.carregar(
            "fornecedores",
            lambda: self._api.listar("fornecedores", limit=1000),
            on_ok=self._fornecedores_recebidos,
        )

    def _fornecedores_recebidos(self, saida: dict) -> None:
        self._fornecedores = [
            (r["id"], r["nome_razao"]) for r in saida.get("data", [])
        ]
        self._preencher_linhas()

    def _carregar(self) -> None:
        item_id = self._item.get("id")
        if not item_id:
            self._lbl_estado.setText("Salve o orçamento antes de gerenciar cotações.")
            self._tabela.estado_vazio("Salve o orçamento para lançar cotações.")
            self._btn_aprovar.setEnabled(False)
            return
        def _chamar() -> dict:
            resposta = self._api._cliente.get(
                f"/v1/os/{self._os_id}/itens/{item_id}/cotacoes",
                headers=self._api._headers(self._api.token),
            )
            return resposta.json()

        tarefas.rodar(
            _chamar,
            on_ok=self._resposta_recebida,
            on_erro=lambda msg: self._lbl_estado.setText(f"Erro ao carregar: {msg}"),
        )

    def _resposta_recebida(self, resposta: dict) -> None:
        self._cotacoes = resposta.get("data") or []
        estado = resposta.get("estado_cotacao")
        snapshot = resposta.get("selecionado") or {}
        if estado == "cotado":
            self._lbl_estado.setText("✓ Cotação aprovada — selecione outra para trocar.")
            estado_sucesso(self._lbl_estado)
        elif estado == "aguardando":
            self._lbl_estado.setText(
                "⚠ Item aguardando cotação — informe o VF e aprove uma opção."
            )
            estado_atencao(self._lbl_estado)
        else:
            self._lbl_estado.setText("")
            estado_muted(self._lbl_estado)
        aplicar_estilo(self._lbl_estado)

        if snapshot:
            self._lbl_snapshot.setText(
                f"VF: R$ {snapshot.get('vf', '?')}  ·  "
                f"CP: R$ {snapshot.get('cp', '?')} (interno)  ·  "
                f"Preço Unit.: R$ {snapshot.get('vo', '?')}"
            )
        else:
            self._lbl_snapshot.clear()
        self._preencher_linhas()

    # ------------------------------------------------------------- tabela

    def _combo_fornecedores(self, selecionado_id=None) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Selecione o fornecedor", None)
        for cid, nome in self._fornecedores:
            combo.addItem(nome, cid)
        if selecionado_id is not None:
            indice = combo.findData(selecionado_id)
            if indice >= 0:
                combo.setCurrentIndex(indice)
        return combo

    @staticmethod
    def _validade_texto(valor) -> str:
        texto = str(valor or "")
        if "-" in texto:
            data = QDate.fromString(texto, "yyyy-MM-dd")
            return data.toString("dd/MM/yyyy") if data.isValid() else texto
        return texto

    def _preencher_linhas(self) -> None:
        self._preenchendo = True
        self._tabela.preencher([
            {
                "fornecedor": "",
                "vf": f"{c.get('vf')}" if c.get("vf") is not None else "(restrito)",
                "prazo": str(c.get("prazo_dias") or ""),
                "validade": self._validade_texto(c.get("validade")),
                "selecionar": "",
            }
            for c in self._cotacoes
        ])
        for linha, cotacao in enumerate(self._cotacoes):
            self._tabela.setCellWidget(
                linha, 0, self._combo_fornecedores(cotacao.get("fornecedor_id"))
            )
            self._marcar_radio(linha, bool(cotacao.get("selecionada")))
        self._tabela.estado_vazio(
            "Nenhuma cotação — adicione um fornecedor abaixo."
            if not self._cotacoes else ""
        )
        self._preenchendo = False

    def _adicionar_linha(self) -> None:
        linha = self._tabela.rowCount()
        self._tabela.insertRow(linha)
        for coluna in (1, 2, 3):
            celula = QTableWidgetItem("")
            celula.setFlags(celula.flags() | Qt.ItemFlag.ItemIsEditable)
            self._tabela.setItem(linha, coluna, celula)
        self._tabela.setCellWidget(linha, 0, self._combo_fornecedores())
        self._marcar_radio(linha, False)
        self._tabela.setCurrentCell(linha, 0)

    def _marcar_radio(self, linha: int, marcado: bool) -> None:
        radio = QRadioButton()
        radio.setToolTip("Selecione a cotação aprovada")
        radio.setChecked(marcado)
        radio.toggled.connect(
            lambda ligado, l=linha: self._radio_mudou(l, ligado)
        )
        self._tabela.setCellWidget(linha, 4, radio)

    def _radio_mudou(self, linha: int, ligado: bool) -> None:
        if not ligado or self._preenchendo:
            return
        for outra in range(self._tabela.rowCount()):
            if outra == linha:
                continue
            radio = self._tabela.cellWidget(outra, 4)
            if isinstance(radio, QRadioButton):
                radio.blockSignals(True)
                radio.setChecked(False)
                radio.blockSignals(False)

    def _celula_alterada(self, _celula) -> None:
        # Edição fica nos itens da tabela; a leitura acontece em `_aprovar`.
        return

    # ------------------------------------------------------------- ações

    def _dados_linha(self, linha: int) -> dict | None:
        combo = self._tabela.cellWidget(linha, 0)
        fornecedor_id = combo.currentData() if isinstance(combo, QComboBox) else None
        vf = para_decimal(self._tabela.item(linha, 1).text() if self._tabela.item(linha, 1) else "")
        if not fornecedor_id or not vf or vf <= 0:
            return None
        prazo_item = self._tabela.item(linha, 2)
        prazo = int(para_decimal(prazo_item.text() if prazo_item else "") or 0) or None
        validade_item = self._tabela.item(linha, 3)
        validade_txt = (validade_item.text() if validade_item else "").strip()
        validade = QDate.fromString(validade_txt, "dd/MM/yyyy")
        if not validade.isValid():
            validade = QDate.fromString(validade_txt, "yyyy-MM-dd")
        return {
            "fornecedor_id": fornecedor_id,
            "vf": str(vf),
            "prazo_dias": prazo,
            "validade": validade.toString("yyyy-MM-dd") if validade.isValid() else None,
        }

    def _aprovar(self) -> None:
        selecionada = -1
        for linha in range(self._tabela.rowCount()):
            radio = self._tabela.cellWidget(linha, 4)
            if isinstance(radio, QRadioButton) and radio.isChecked():
                selecionada = linha
                break
        if selecionada < 0:
            QMessageBox.information(
                self, "Cotação", "Selecione a cotação aprovada pelo rádio."
            )
            return
        dados = self._dados_linha(selecionada)
        if dados is None:
            QMessageBox.warning(
                self, "Cotação", "Informe fornecedor e VF da cotação selecionada."
            )
            return

        # Cotação existente e intacta: apenas marca como selecionada. Se o VF
        # mudou, cria uma nova (o snapshot é imutável por definição).
        existente = (
            self._cotacoes[selecionada]
            if 0 <= selecionada < len(self._cotacoes) else None
        )
        alterada = bool(
            existente is None
            or para_decimal(existente.get("vf")) != para_decimal(dados["vf"])
            or (existente.get("prazo_dias") or None) != dados["prazo_dias"]
            or (existente.get("validade") or None) != dados["validade"]
        )
        operacoes: list[tuple[str, object]] = []
        for linha in range(len(self._cotacoes), self._tabela.rowCount()):
            if linha == selecionada:
                continue
            comparativo = self._dados_linha(linha)
            if comparativo:
                operacoes.append(("criar", comparativo))
        if existente is not None and not alterada:
            operacoes.append(("selecionar", existente["id"]))
        else:
            operacoes.append(("criar", {**dados, "selecionada": True}))

        self._btn_aprovar.setEnabled(False)
        self._btn_aprovar.setText("Aprovando…")
        self._executar_operacoes(operacoes)

    def _executar_operacoes(self, operacoes: list[tuple[str, object]]) -> None:
        if not operacoes:
            self._buscar_aprovacao()
            return
        tipo, valor = operacoes[0]

        def falha(msg: str) -> None:
            self._btn_aprovar.setEnabled(True)
            self._btn_aprovar.setText("Aprovar Cotação")
            QMessageBox.critical(self, "Cotação", msg)

        if tipo == "selecionar":
            acao = lambda: self._api.selecionar_cotacao(
                self._os_id, self._item["id"], valor
            )
        else:
            acao = lambda: self._api.lancar_cotacao(
                self._os_id, self._item["id"], valor
            )

        def proximo(_resposta) -> None:
            self._executar_operacoes(operacoes[1:])

        tarefas.rodar(acao, on_ok=proximo, on_erro=falha)

    def _buscar_aprovacao(self) -> None:
        def ok(resposta: dict) -> None:
            self.aprovado = resposta.get("selecionado") or {}
            self._btn_aprovar.setEnabled(True)
            self._btn_aprovar.setText("Aprovar Cotação")
            self.accept()

        def chamar() -> dict:
            resposta = self._api._cliente.get(
                f"/v1/os/{self._os_id}/itens/{self._item['id']}/cotacoes",
                headers=self._api._headers(self._api.token),
            )
            return resposta.json()

        tarefas.rodar(chamar, on_ok=ok, on_erro=lambda _msg: self.accept())


# ------------------------------------------------------- diálogo de arte (M3)

_ARTE_CHAVES = ["versao", "nome_arquivo", "tamanho_bytes", "criado_em"]
_ARTE_ROTULOS = ["Versão", "Arquivo", "Tamanho", "Enviada em"]

# Espelha o backend (NFR de arquivos): extensões executáveis bloqueadas.
_ARTE_EXTENSOES_BLOQUEADAS = {
    ".exe", ".bat", ".cmd", ".sh", ".ps1", ".msi", ".dll",
    ".com", ".scr", ".vbs", ".js",
}
_ARTE_MAX_MB = 50  # o servidor rejeita acima disso (400) — antecipamos o aviso

_ARTE_ESTADOS = {
    "sem_arte": ("Nenhuma arte enviada — envie a primeira versão.", "muted"),
    "aguardando_aprovacao": (
        "⚠ Aguardando aprovação do cliente.", "atencao",
    ),
    "ajuste_solicitado": (
        "⚠ Ajuste solicitado pelo cliente — reenvie a arte corrigida.", "atencao",
    ),
    "aprovada": ("✓ Arte aprovada pelo cliente.", "success"),
}


def _arte_quando(iso: str | None) -> str:
    """`2026-10-27T14:23:45` → `27/10/2026 14:23` (vazio → `—`)."""
    return formatar_datahora(iso) or "—"


def _arte_tamanho(bytes_: object) -> str:
    try:
        n = int(bytes_)
    except (TypeError, ValueError):
        return "—"
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


class DialogoArte(QDialog):
    """Arte, prova e aprovação da O.S. (M3, PRD v3.0 §3.5).

    Quatro zonas:
    - **Estado** derivado da última versão (sem arte / aguardando aprovação /
      ajuste solicitado / aprovada);
    - **Versões** em tabela (v1, v2… — a mais recente primeiro);
    - **Ações**: enviar nova versão (upload), aprovar marcada, solicitar
      ajuste (com comentário obrigatório) e gerar link de prova (token de uso
      único com expiração — o relay da decisão D-03 resolve no futuro).
    """

    def __init__(self, parent, api, os_id: int) -> None:
        super().__init__(parent)
        self._api = api
        self._os_id = os_id
        self._versoes: list[dict] = []

        self.setWindowTitle("Arte, Prova e Aprovação")
        self.setMinimumSize(640, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        titulo = QLabel(f"O.S. #{os_id} — versões da arte")
        titulo.setObjectName("subtitulo")
        root.addWidget(titulo)

        # --- estado derivado (§3.5)
        self._lbl_estado = QLabel("Carregando…")
        estado_muted(self._lbl_estado)
        root.addWidget(self._lbl_estado)

        # --- versões
        self._tabela = TabelaDensa(_ARTE_CHAVES, _ARTE_ROTULOS)
        self._tabela.setMinimumHeight(160)
        root.addWidget(self._tabela, 1)

        # --- botões
        botoes = QHBoxLayout()
        botoes.setSpacing(8)

        self._btn_enviar = QPushButton("Enviar nova versão…")
        estado_primario(self._btn_enviar)
        self._btn_enviar.clicked.connect(self._enviar)
        botoes.addWidget(self._btn_enviar)

        self._btn_aprovar = QPushButton("Aprovar marcada")
        self._btn_aprovar.clicked.connect(self._aprovar)
        botoes.addWidget(self._btn_aprovar)

        self._btn_ajuste = QPushButton("Solicitar ajuste…")
        self._btn_ajuste.clicked.connect(self._ajuste)
        botoes.addWidget(self._btn_ajuste)

        self._btn_link = QPushButton("Gerar link de prova")
        self._btn_link.clicked.connect(self._link)
        botoes.addWidget(self._btn_link)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        botoes.addStretch(1)
        botoes.addWidget(fechar)
        root.addLayout(botoes)

        self._carregar()

    # ------------------------------------------------------------- dados

    def _carregar(self) -> None:
        os_id = self._os_id
        tarefas.rodar(
            lambda: self._api.arte(os_id),
            on_ok=self._preencher,
            on_erro=lambda msg: self._lbl_estado.setText(f"Erro ao carregar: {msg}"),
        )

    def _preencher(self, resposta: dict) -> None:
        self._versoes = resposta.get("data") or []
        estado = resposta.get("estado") or "sem_arte"

        texto, role = _ARTE_ESTADOS.get(estado, (estado, "muted"))
        self._lbl_estado.setText(texto)
        if role == "muted":
            estado_muted(self._lbl_estado)
        elif role == "success":
            estado_sucesso(self._lbl_estado)
        elif role == "atencao":
            estado_atencao(self._lbl_estado)
        elif role == "error":
            estado_erro(self._lbl_estado)
        else:
            aplicar_estilo(self._lbl_estado)
        aplicar_estilo(self._lbl_estado)

        linhas = []
        for v in self._versoes:
            linhas.append({
                "versao": f"v{v.get('versao', '?')}",
                "nome_arquivo": v.get("nome_arquivo", "?"),
                "tamanho_bytes": _arte_tamanho(v.get("tamanho_bytes")),
                "criado_em": _arte_quando(v.get("criado_em")),
            })
        self._tabela.preencher(linhas)
        tem = bool(self._versoes)
        self._btn_aprovar.setEnabled(tem)
        self._btn_ajuste.setEnabled(tem)

    # ------------------------------------------------------------- ações

    def _enviar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar arquivo de arte",
            "",
            "Arquivos de arte (*.png *.jpg *.jpeg *.pdf *.svg *.tif *.tiff "
            "*.psd *.ai *.cdr *.zip);;Todos os arquivos (*)",
        )
        if not caminho:
            return

        ext = Path(caminho).suffix.lower()
        if ext in _ARTE_EXTENSOES_BLOQUEADAS:
            QMessageBox.warning(
                self, "Arte", f"Extensão {ext} não é permitida para arte."
            )
            return
        tamanho = Path(caminho).stat().st_size
        if tamanho <= 0:
            QMessageBox.warning(self, "Arte", "O arquivo está vazio.")
            return
        if tamanho > _ARTE_MAX_MB * 1024 * 1024:
            QMessageBox.warning(
                self, "Arte", f"Arquivo maior que {_ARTE_MAX_MB} MB."
            )
            return

        os_id = self._os_id
        self._btn_enviar.setEnabled(False)
        self._btn_enviar.setText("Enviando…")

        def ok(_resultado) -> None:
            self._btn_enviar.setEnabled(True)
            self._btn_enviar.setText("Enviar nova versão…")
            self._carregar()

        def erro(msg: str) -> None:
            self._btn_enviar.setEnabled(True)
            self._btn_enviar.setText("Enviar nova versão…")
            QMessageBox.critical(self, "Arte", msg)

        tarefas.rodar(
            lambda: self._api.enviar_arte(os_id, caminho),
            on_ok=ok,
            on_erro=erro,
        )

    def _versao_marcada(self) -> dict | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._versoes):
            QMessageBox.information(
                self, "Arte", "Selecione uma versão na tabela."
            )
            return None
        return self._versoes[linha]

    def _aprovar(self) -> None:
        versao = self._versao_marcada()
        if not versao:
            return
        os_id, versao_id = self._os_id, versao.get("id")
        self._btn_aprovar.setEnabled(False)

        def ok(_resultado) -> None:
            self._btn_aprovar.setEnabled(True)
            self._carregar()

        def erro(msg: str) -> None:
            self._btn_aprovar.setEnabled(True)
            QMessageBox.critical(self, "Arte", msg)

        tarefas.rodar(
            lambda: self._api.decidir_arte(os_id, versao_id, "aprovada"),
            on_ok=ok,
            on_erro=erro,
        )

    def _ajuste(self) -> None:
        versao = self._versao_marcada()
        if not versao:
            return
        comentario, confirmado = QInputDialog.getMultiLineText(
            self,
            "Solicitar ajuste",
            "O que o cliente pediu para ajustar nesta versão?",
        )
        comentario = (comentario or "").strip()
        if not confirmado or not comentario:
            if confirmado:
                QMessageBox.warning(
                    self, "Arte", "Descreva o ajuste solicitado pelo cliente."
                )
            return

        os_id, versao_id = self._os_id, versao.get("id")
        self._btn_ajuste.setEnabled(False)

        def ok(_resultado) -> None:
            self._btn_ajuste.setEnabled(True)
            self._carregar()

        def erro(msg: str) -> None:
            self._btn_ajuste.setEnabled(True)
            QMessageBox.critical(self, "Arte", msg)

        tarefas.rodar(
            lambda: self._api.decidir_arte(os_id, versao_id, "ajuste", comentario),
            on_ok=ok,
            on_erro=erro,
        )

    def _link(self) -> None:
        os_id = self._os_id
        self._btn_link.setEnabled(False)

        def ok(link: dict) -> None:
            self._btn_link.setEnabled(True)
            token = link.get("token", "?")
            expira = _arte_quando(link.get("expira_em"))
            from PySide6.QtWidgets import QApplication

            QApplication.clipboard().setText(token)
            QMessageBox.information(
                self,
                "Link de prova",
                f"Token: {token}\n\nExpira em {expira} (uso único).\n"
                "O token já foi copiado — cole no envio ao cliente.",
            )

        def erro(msg: str) -> None:
            self._btn_link.setEnabled(True)
            QMessageBox.critical(self, "Arte", msg)

        tarefas.rodar(
            lambda: self._api.link_arte(os_id),
            on_ok=ok,
            on_erro=erro,
        )


class PaginaOS(CondicaoPagamentoCliente, PaginaCrud):
    ENTIDADE = "os"
    TIPO = "os"
    ROTULO_PAGINA = "Ordens de Serviço"
    ROTULO_NOVO = "Nova Ordem de Serviço"
    GRUPO_LISTA = "FILA OPERACIONAL"
    LUGAR_BUSCA = "Buscar por Nº da O.S. ou nome do cliente..."
    CAMPO_NOME = "cliente_nome"
    # P1#12: remove redundância O.S./Nº e acrescenta entrada + indicador de arte.
    CHAVES = ["numero", "cliente_nome", "status", "data_emissao", "data_previsao_entrega", "valor_total", "arte_pendente"]
    COLUNAS = ["Nº", "Cliente", "Status", "Entrada", "Prazo", "Total", "Arte"]
    PESOS = [1, 4, 2, 2, 2, 2, 1]
    CHAVE_FILTRO = "status"
    # P0#2 (revisão PDV+Hist+OS): em 1024px o formulário ocupa a tela inteira.
    FORM_EM_TELA_CHEIA = True
    FILTROS = [
        ("", "Todas"),
        ("aberto", "Abertas"),
        ("aguardando_arte", "Aguardando arte"),  # M3 (§3.5)
        ("aguardando_aprovacao", "Aguardando aprovação"),  # M3 (§3.5)
        ("producao", "Em Produção"),
        ("pronta", "Prontas"),
        ("entregue", "Entregues"),
        ("cancelado", "Canceladas"),
        ("__atrasada", "Atrasadas"),
        ("__entrega_hoje", "Entrega hoje"),
    ]

    def __init__(self, api, modo_leitura: bool = False) -> None:
        self._rotulos_filtro_base = {v: r for v, r in self.FILTROS}
        self._contadores_os = {"atrasada": None, "entrega_hoje": None}
        super().__init__(api, modo_leitura)
        self._lbl_contadores_os = QLabel("")
        estado_muted(self._lbl_contadores_os)
        self._lbl_contadores_os.setWordWrap(True)
        if getattr(self, "_filtros_widget", None) is not None:
            # Abaixo da barra de filtros (não dentro do FlowLayout, onde o
            # rótulo com quebra de linha sobrepunha os botões em 1024px).
            barra = self._filtros_widget.parentWidget()
            if barra is not None and barra.layout() is not None:
                barra.layout().addWidget(self._lbl_contadores_os)
        self._carregar_clientes_flags()
        self._carregar_funcionarios()
        self._atualizar_contadores_os()
        # Consistência de ação principal no fluxo de OS
        if hasattr(self, "_btn_salvar"):
            acao = "orçamento" if self.TIPO == "orcamento" else "ordem de serviço"
            self._btn_salvar.setToolTip(f"Salvar {acao} (F10)")

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._iniciar_condicao_pagamento()  # flags de pagamento por cliente
        # Fase 1: combobox com autocomplete remoto (debounce) e autopreenchimento.
        self._cliente = CampoClienteAutocomplete("Cliente", self._api).obrigatorio()
        self._vendedor = CampoCombo("Vendedor", [])
        self._atendente = CampoCombo("Atendente", [])
        # Contato preenchido automaticamente ao selecionar cliente cadastrado.
        from printgest.ui.formulario import CampoTelefone

        self._telefone_cliente = CampoTelefone("Telefone do cliente")
        self._email_cliente = CampoTexto("E-mail do cliente", maximo=120)
        self._salvar_novo_cliente = CampoCheck("Salvar como novo cliente")
        # P1#9: data + hora (backend persiste data; hora melhora UX de planejamento)
        self._previsao = CampoDataHora("Previsão de Entrega", obrigatorio=False)
        self._forma = CampoCombo("Forma de Pagamento", FORMAS_PAGAMENTO)
        self._valor_sinal = CampoValor("Sinal (valor)")
        self._sinal_pct = CampoTexto("Sinal (%)", maximo=6)
        self._sinal_pct.widget.setPlaceholderText("Ex.: 30")
        self._forma_sinal = CampoCombo("Forma do Sinal", FORMAS_PAGAMENTO)
        self._desconto = CampoValor("Desconto")
        self._valor_sinal.edicao.setPlaceholderText("0,00")
        self._desconto.edicao.setPlaceholderText("0,00")
        self._obs = CampoArea("Observações", linhas=2)
        self._pagamento_confirmado = CampoCheck("Pagamento já recebido")
        self._itens = GradeItens("", api=self._api)
        # P0#2 (refino): em tela cheia, a grade de itens precisa de área útil
        # sem comprimir o restante do formulário em 1024x768.
        self._itens.setMinimumHeight(260)
        self._itens._tabela.setMinimumHeight(170)

        # P1#11: combos pesquisáveis (digitação filtra opções).
        # Cliente agora tem autocomplete remoto próprio — só vendedor/atendente
        # usam o completer local.
        for campo, placeholder in (
            (self._vendedor, "Buscar/selecionar vendedor"),
            (self._atendente, "Buscar/selecionar atendente"),
        ):
            combo = campo.widget
            combo.setEditable(True)
            combo.setInsertPolicy(combo.InsertPolicy.NoInsert)
            combo.setPlaceholderText(placeholder)
            comp = combo.completer()
            if comp is not None:
                comp.setFilterMode(Qt.MatchFlag.MatchContains)
                comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        # Ação rápida "Novo cliente" inline (P1#11).
        self._btn_novo_cliente = QPushButton("Novo cliente")
        self._btn_novo_cliente.setObjectName("acaoLinha")
        self._btn_novo_cliente.clicked.connect(self._novo_cliente_inline)
        # Esquerda: cliente + ação inline + opção de cadastro rápido.
        cliente_widget = QWidget()
        coluna_cliente = QVBoxLayout(cliente_widget)
        coluna_cliente.setContentsMargins(0, 0, 0, 0)
        coluna_cliente.setSpacing(4)
        linha_cli = QHBoxLayout()
        linha_cli.setSpacing(6)
        linha_cli.addWidget(self._cliente.widget, 1)
        linha_cli.addWidget(self._btn_novo_cliente)
        coluna_cliente.addLayout(linha_cli)
        coluna_cliente.addWidget(self._salvar_novo_cliente.widget)
        cliente_widget.setFocusProxy(self._cliente.widget)

        # Direita: telefone e e-mail empilhados, lado a lado com o cliente.
        contato_widget = QWidget()
        coluna_contato = QVBoxLayout(contato_widget)
        coluna_contato.setContentsMargins(0, 0, 0, 0)
        coluna_contato.setSpacing(4)
        for campo in (self._telefone_cliente, self._email_cliente):
            if campo.rotulo_widget is not None:
                coluna_contato.addWidget(campo.rotulo_widget)
            coluna_contato.addWidget(campo.widget)

        class _CampoClienteWrap:
            largo = False

            def __init__(self, campo, widget, botao, check):
                self._campo = campo
                self._botao = botao
                self._check = check
                self.rotulo_widget = campo.rotulo_widget
                self.widget = widget

            def valor(self):
                return self._campo.valor()

            def definir(self, v):
                self._campo.definir(v)
                self._check.definir(False)

            def habilitar(self, ligado: bool):
                self._campo.habilitar(ligado)
                self._botao.setEnabled(ligado)
                self._check.habilitar(ligado)

            def obrigatorio(self):
                self._campo.obrigatorio()
                return self

        class _CampoContatoWrap:
            largo = False
            rotulo_widget = None  # os rótulos já estão dentro do composite

            def __init__(self, campos, widget):
                self._campos = campos
                self.widget = widget

            def valor(self):
                return None

            def definir(self, _v):
                for campo in self._campos:
                    campo.definir(None)

            def habilitar(self, ligado: bool):
                for campo in self._campos:
                    campo.habilitar(ligado)

        self._cliente_campo = _CampoClienteWrap(
            self._cliente,
            cliente_widget,
            self._btn_novo_cliente,
            self._salvar_novo_cliente,
        )
        self._contato_campo = _CampoContatoWrap(
            (self._telefone_cliente, self._email_cliente), contato_widget
        )

        financeiro = [
            self._previsao,
            self._forma,
            self._valor_sinal,
            self._sinal_pct,
            self._forma_sinal,
            self._desconto,
            self._obs,
        ]
        # Orçamento não tem "pagamento recebido": o sinal já resolve a exigência.
        if self.TIPO == "os":
            financeiro.append(self._pagamento_confirmado)

        secoes = [(
            "Cliente & Equipe",
            [
                self._cliente_campo,
                self._contato_campo,
                self._vendedor,
                self._atendente,
            ],
        )]
        # No orçamento os itens são a tela principal; prazos vêm depois,
        # num painel recolhível (fluxo progressivo).
        if self.TIPO == "orcamento":
            secoes.extend([
                ("Itens", [self._itens]),
                ("Prazos & Financeiro", financeiro),
            ])
        else:
            secoes.extend([
                ("Prazos & Financeiro", financeiro),
                ("Itens", [self._itens]),
            ])
        return secoes

    def _conectar_campos(self) -> None:
        self._cliente.combo.currentIndexChanged.connect(self._ao_mudar_cliente_os)
        # Ao selecionar um cliente, preenche telefone/e-mail (e desmarca "novo").
        self._cliente.combo.currentIndexChanged.connect(self._cliente_selecionado_os)
        # Nome digitado sem correspondência ⇒ sugerir explicitamente o cadastro
        # de cliente novo (o campo mostra o texto, mas nenhum id está selecionado).
        self._cliente.correspondencia_mudou.connect(self._cliente_correspondencia_mudou)
        self._desconto.edicao.textChanged.connect(self._atualizar_totais_os)
        if hasattr(self._valor_sinal, "edicao"):
            self._valor_sinal.edicao.textChanged.connect(self._atualizar_totais_os)
        self._itens.alterado.connect(self._atualizar_totais_os)
        self._itens.cotacao_solicitada.connect(self._abrir_cotacoes_item)

    def _cliente_correspondencia_mudou(self, sem_correspondencia: bool) -> None:
        # Registro existente pode ter cliente avulso legítimo: não transformar
        # a busca em cadastro novo sem autorização explícita do operador.
        if self._editando_id is not None:
            return
        self._salvar_novo_cliente.definir(
            bool(sem_correspondencia and self._cliente.texto)
        )

    def _ao_mudar_cliente_os(self) -> None:
        self._cliente_mudou()
        self._atualizar_totais_os()

    def _clientes_flags_recebidos(self, saida: dict) -> None:
        """Carrega flags E dados de contato para autopreenchimento local."""
        super()._clientes_flags_recebidos(saida)
        dados = saida.get("data", [])
        self._cliente.alterar_opcoes(
            [(r["id"], r.get("nome_razao", "")) for r in dados],
            {r["id"]: r for r in dados if r.get("id") is not None},
        )

    def _cliente_selecionado_os(self) -> None:
        """Autopreenche contato quando o cliente é selecionado."""
        cliente = self._cliente.cliente_selecionado
        if cliente is None:
            return
        self._telefone_cliente.definir(cliente.get("telefone"))
        self._email_cliente.definir(cliente.get("email"))
        self._salvar_novo_cliente.definir(False)

    def _novo_cliente_inline(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Novo cliente")
        form = QFormLayout(dlg)
        nome = QLineEdit(); nome.setPlaceholderText("Nome / Razão social")
        doc = QLineEdit(); doc.setPlaceholderText("CPF/CNPJ (opcional)")
        tel = QLineEdit(); tel.setPlaceholderText("Telefone (opcional)")
        form.addRow("Nome*", nome)
        form.addRow("Documento", doc)
        form.addRow("Telefone", tel)
        botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(botoes)
        botoes.rejected.connect(dlg.reject)

        def salvar():
            n = nome.text().strip()
            if not n:
                QMessageBox.warning(dlg, "Cliente", "Informe o nome do cliente.")
                return
            payload = {"nome_razao": n, "tipo_pessoa": "PF"}
            if doc.text().strip():
                payload["cpf_cnpj"] = doc.text().strip()
            if tel.text().strip():
                payload["telefone"] = tel.text().strip()
            try:
                criado = self._api.criar("clientes", payload)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(dlg, "Cliente", str(exc))
                return
            dado = criado.get("data", criado) if isinstance(criado, dict) else {}
            cid = dado.get("id")
            rot = dado.get("nome_razao") or n
            if cid is not None:
                self._cliente_flags[cid] = (
                    bool(dado.get("pagamento_adiantado")),
                    bool(dado.get("sinal")),
                    dado.get("sinal_pct"),
                )
                combo = self._cliente.widget
                idx = combo.findData(cid)
                if idx < 0:
                    combo.addItem(rot, cid)
                    idx = combo.findData(cid)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self._carregar_clientes_flags()
            dlg.accept()

        botoes.accepted.connect(salvar)
        dlg.exec()

    def _rodape_pos_acoes(self, layout: QHBoxLayout) -> None:
        # P0#2 (refino): totais fixos no rodapé do formulário.
        self._lbl_totais_os = QLabel("Itens (0): R$ 0,00 · Desconto: R$ 0,00 · TOTAL: R$ 0,00")
        self._lbl_totais_os.setObjectName("resumoFinanceiro")
        estado_muted(self._lbl_totais_os)
        self._lbl_totais_os.setWordWrap(True)
        self._lbl_totais_os.setToolTip(
            "Resumo financeiro: itens, desconto, total e (quando aplicável) sinal/saldo"
        )
        layout.insertWidget(0, self._lbl_totais_os, 1)
        self._atualizar_totais_os()

    def _atualizar_totais_os(self) -> None:
        if not hasattr(self, "_lbl_totais_os") or not hasattr(self, "_itens"):
            return
        from decimal import Decimal
        from printgest.ui.formulario import formatar_moeda, para_decimal

        subtotal = Decimal("0")
        itens = self._itens.valor()
        for item in itens:
            qtd = para_decimal(item.get("quantidade")) or Decimal("0")
            unit = para_decimal(item.get("valor_unitario")) or Decimal("0")
            desc_item = para_decimal(item.get("desconto")) or Decimal("0")
            subtotal += (qtd * unit) - desc_item
        if subtotal < 0:
            subtotal = Decimal("0")
        desconto = para_decimal(self._desconto.valor()) or Decimal("0")
        total = subtotal - desconto
        if total < 0:
            total = Decimal("0")
        saldo_txt = ""
        try:
            sinal_informado = para_decimal(self._valor_sinal.valor()) if hasattr(self, "_valor_sinal") else None
            if sinal_informado is not None:
                saldo = total - sinal_informado
                if saldo < 0:
                    saldo = Decimal("0")
                saldo_txt = f" · Sinal {formatar_moeda(str(sinal_informado))} · Saldo {formatar_moeda(str(saldo))}"
            else:
                exigencia = self._exigencia_pendente()
                if exigencia:
                    adiantado, sinal, pct = self._cliente_flags.get(self._cliente.valor(), (False, False, None))
                    if sinal and pct is not None:
                        sinal_val = (total * (para_decimal(pct) or Decimal("0")) / Decimal("100")).quantize(Decimal("0.01"))
                        saldo = total - sinal_val
                        if saldo < 0:
                            saldo = Decimal("0")
                        saldo_txt = f" · Sinal {formatar_moeda(str(sinal_val))} · Saldo {formatar_moeda(str(saldo))}"
                    elif adiantado:
                        saldo_txt = f" · Saldo {formatar_moeda('0')}"
        except Exception:
            saldo_txt = ""
        self._lbl_totais_os.setText(
            f"Itens ({len(itens)}): {formatar_moeda(str(subtotal))} &nbsp;·&nbsp; "
            f"Desconto: {formatar_moeda(str(desconto))} &nbsp;·&nbsp; "
            f'<span style="color:#0071E3; font-weight:700">'
            f"TOTAL: {formatar_moeda(str(total))}</span>{saldo_txt}"
        )

    def _padroes_do_form(self) -> None:
        from datetime import datetime

        self._desconto.definir(None)
        if hasattr(self, "_valor_sinal"):
            self._valor_sinal.definir(None)
        if hasattr(self, "_forma_sinal"):
            self._forma_sinal.definir(None)
        self._pagamento_confirmado.definir(False)
        # P1#9: previsão com data/hora padrão.
        self._previsao.definir(datetime.now().replace(hour=9, minute=0, second=0, microsecond=0))
        # P1#11: padrões vendedor/atendente pelo usuário logado (quando houver correspondência).
        self._aplicar_padrao_usuario()
        self._cliente_mudou()
        self._atualizar_totais_os()

    def _aplicar_padrao_usuario(self) -> None:
        # `Api.usuario` é @property (dict), não método. Chamá-lo como função
        # lançava TypeError engolido pelo except — os padrões nunca eram aplicados.
        usuario = getattr(self._api, "usuario", None) or {}
        funcionario_id = usuario.get("funcionario_id")
        nome = str(usuario.get("nome") or "").strip().lower()
        login = str(usuario.get("login") or "").strip().lower()
        if not (funcionario_id or nome or login):
            return
        for campo in (self._vendedor, self._atendente):
            if not hasattr(campo, "widget"):
                continue
            combo = campo.widget
            if funcionario_id is not None:
                idx = combo.findData(funcionario_id)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    continue
            for i in range(combo.count()):
                rot = str(combo.itemText(i) or "").strip().lower()
                if rot and (rot == nome or rot == login):
                    combo.setCurrentIndex(i)
                    break

    # ---------------------------------------------------------------- busca

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        status = self._filtro or None
        atrasada = None
        entrega_hoje = None
        if self._filtro == "__atrasada":
            status = None
            atrasada = True
        elif self._filtro == "__entrega_hoje":
            status = None
            entrega_hoje = True
        return self._api.listar_os(
            q=q,
            status=status,
            tipo=self.TIPO,
            atrasada=atrasada,
            entrega_hoje=entrega_hoje,
            limit=LOTE,
            offset=offset,
        )

    def _recebidos(self, q: str, offset: int, saida: dict) -> None:
        super()._recebidos(q, offset, saida)
        self._atualizar_contadores_os(q)

    def _atualizar_contadores_os(self, q: str = "") -> None:
        if not hasattr(self, "_btn_filtros"):
            return

        def _buscar(flag: str):
            try:
                params = {"q": q, "tipo": self.TIPO, "limit": 1, "offset": 0}
                if flag == "atrasada":
                    params["atrasada"] = True
                elif flag == "entrega_hoje":
                    params["entrega_hoje"] = True
                return self._api.listar_com_filtros("os", **params)
            except Exception:
                return {"total": None}

        def _aplicar(atrasada, entrega_hoje):
            tot_a = (atrasada or {}).get("total")
            tot_h = (entrega_hoje or {}).get("total")
            self._contadores_os["atrasada"] = tot_a
            self._contadores_os["entrega_hoje"] = tot_h
            if "__atrasada" in self._btn_filtros and tot_a is not None:
                base = self._rotulos_filtro_base.get("__atrasada", "Atrasadas")
                self._btn_filtros["__atrasada"].setText(f"{base} ({tot_a})")
                self._btn_filtros["__atrasada"].setToolTip(
                    "Ordens com previsão vencida e ainda não concluídas"
                )
            if "__entrega_hoje" in self._btn_filtros and tot_h is not None:
                base = self._rotulos_filtro_base.get("__entrega_hoje", "Entrega hoje")
                self._btn_filtros["__entrega_hoje"].setText(f"{base} ({tot_h})")
                self._btn_filtros["__entrega_hoje"].setToolTip(
                    "Ordens com previsão de entrega para hoje"
                )
            if hasattr(self, "_lbl_contadores_os"):
                partes = []
                if tot_a is not None:
                    partes.append(f"Atrasadas: {tot_a}")
                if tot_h is not None:
                    partes.append(f"Entrega hoje: {tot_h}")
                self._lbl_contadores_os.setText(" · ".join(partes))

        # duas consultas leves em paralelo (sequenciais via callbacks)
        def ok_atrasada(r1):
            def ok_hoje(r2):
                _aplicar(r1, r2)
            tarefas.rodar(lambda: _buscar("entrega_hoje"), on_ok=ok_hoje, on_erro=lambda _m: _aplicar(r1, {"total": None}))
        tarefas.rodar(lambda: _buscar("atrasada"), on_ok=ok_atrasada, on_erro=lambda _m: None)

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "cliente_nome":
            return str(
                dado.get("cliente_nome") or dado.get("cliente_nome_avulso") or "—"
            )
        if chave == "status":
            valor = str(dado.get("status", "") or "")
            rotulos = {
                "aberto": "Aberta",
                "aguardando_arte": "Aguardando arte",
                "aguardando_aprovacao": "Aguardando aprovação",
                "producao": "Em produção",
                "pronta": "Pronta",
                "entregue": "Entregue",
                "cancelado": "Cancelada",
                "convertido": "Convertida",
            }
            return rotulos.get(valor, valor.replace("_", " ").strip().capitalize() or "")
        if chave == "valor_total":
            return formatar_moeda(dado.get("valor_total"))
        if chave == "data_previsao_entrega":
            from datetime import date

            valor = dado.get("data_previsao_entrega")
            texto = formatar_data_iso(valor)
            if not texto:
                return ""
            try:
                dt = date.fromisoformat(str(valor)[:10])
            except Exception:
                return texto
            status = str(dado.get("status") or "")
            if status not in {"entregue", "cancelado", "convertido"}:
                hoje = date.today()
                if dt < hoje:
                    return f"{texto} (Atrasada)"
                if dt == hoje:
                    return f"{texto} (Hoje)"
            return texto
        if chave == "data_emissao":
            return formatar_data_iso(dado.get("data_emissao") or dado.get("created_at"))
        if chave == "arte_pendente":
            status = str(dado.get("status") or "")
            return "Pendente" if status in {"aguardando_arte", "aguardando_aprovacao"} else "—"
        return super()._formatar_texto(dado, chave)

    # ------------------------------------------------------------ carregar

    def _carregar_funcionarios(self) -> None:
        catalogos.carregar(
            "funcionarios",
            lambda: self._api.listar("funcionarios", limit=1000),
            on_ok=self._funcionarios_recebidos,
        )

    def _funcionarios_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", [])
        vendedores = [r for r in dados if r.get("e_vendedor")] or dados
        atendentes = [r for r in dados if r.get("e_atendente")] or dados
        self._vendedor.alterar_opcoes([(r["id"], r["nome"]) for r in vendedores])
        self._atendente.alterar_opcoes([(r["id"], r["nome"]) for r in atendentes])
        if self._editando_id is None:
            self._aplicar_padrao_usuario()

    def _preencher_campos(self, dado: dict) -> None:
        cid = dado.get("cliente_id")
        if cid is not None:
            self._cliente.definir(cid)
        else:
            # Bloqueia sinais: `editTextChanged` agendaria a busca remota, que
            # repovoa o combo e auto-seleciona o primeiro cliente, apagando ou
            # trocando o nome avulso gravado no orçamento.
            combo = self._cliente.combo
            combo.blockSignals(True)
            combo.setEditText(dado.get("cliente_nome_avulso") or "")
            combo.blockSignals(False)
        self._vendedor.definir(dado.get("vendedor_id"))
        self._atendente.definir(dado.get("atendente_id"))
        previsao = dado.get("data_previsao_entrega")
        if isinstance(previsao, str) and len(previsao) == 10:
            previsao = f"{previsao}T09:00:00"
        self._previsao.definir(previsao)
        self._forma.definir(dado.get("forma_pagamento"))
        if hasattr(self, "_valor_sinal"):
            self._valor_sinal.definir(dado.get("valor_sinal"))
        if hasattr(self, "_forma_sinal"):
            self._forma_sinal.definir(dado.get("forma_sinal"))
        self._desconto.definir(dado.get("desconto"))
        self._sinal_pct.definir(None)  # backend persiste só o valor em reais
        self._obs.definir(dado.get("observacoes"))
        self._pagamento_confirmado.definir(False)
        self._itens.definir(dado.get("itens") or [])
        self._atualizar_totais_os()

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        from decimal import Decimal

        if not self._cliente.valor() and not self._cliente.texto:
            return ("Informe o cliente.", self._cliente)
        if not self._itens.valor():
            return ("Adicione ao menos um item.", self._itens.widget)
        percentual = para_decimal(self._sinal_pct.valor())
        if percentual is not None and not Decimal("0") <= percentual <= Decimal("100"):
            return ("O sinal em percentual deve estar entre 0 e 100.", self._sinal_pct)
        # P1#11 (refino): validações financeiras defensivas do sinal.
        if hasattr(self, "_valor_sinal") and hasattr(self, "_forma_sinal"):
            from decimal import Decimal

            sinal = para_decimal(self._valor_sinal.valor()) or Decimal("0")
            if sinal > 0 and not self._forma_sinal.valor():
                return ("Informe a forma de pagamento do sinal.", self._forma_sinal)
            if sinal > 0:
                subtotal = Decimal("0")
                for item in self._itens.valor():
                    qtd = para_decimal(item.get("quantidade")) or Decimal("0")
                    unit = para_decimal(item.get("valor_unitario")) or Decimal("0")
                    desc_item = para_decimal(item.get("desconto")) or Decimal("0")
                    subtotal += (qtd * unit) - desc_item
                desconto = para_decimal(self._desconto.valor()) or Decimal("0")
                total = max(Decimal("0"), subtotal - desconto)
                if sinal > total:
                    return (
                        "O sinal não pode ser maior que o total da O.S.",
                        self._valor_sinal,
                    )
        if self._editando_id is None and self.TIPO == "os":
            exigencia = self._exigencia_pendente()
            if exigencia:
                return (
                    f"O cliente exige {exigencia}. Marque 'Pagamento já recebido' "
                    "para lançar a O.S.",
                    self._pagamento_confirmado,
                )
        return None

    def _salvar(self) -> None:
        """Cria o cliente marcado como novo antes de salvar a O.S./Orçamento."""
        nome = self._cliente.texto
        sem_cliente = self._cliente.valor() is None
        # Cadastro rápido: se o operador digitou nome/contato mas não marcou o
        # checkbox, pergunta na hora de salvar (evita o clique extra no formulário).
        if (
            self._editando_id is None
            and sem_cliente
            and nome
            and not self._salvar_novo_cliente.valor()
        ):
            resposta = QMessageBox.question(
                self,
                "Cliente",
                f'Cadastrar “{nome}” como novo cliente?\n\n'
                "Escolha “Não” para salvar com cliente avulso.",
            )
            if resposta == QMessageBox.StandardButton.Yes:
                self._salvar_novo_cliente.definir(True)
        if not self._salvar_novo_cliente.valor() or not sem_cliente:
            super()._salvar()
            return
        if not nome:
            QMessageBox.warning(
                self, "Cliente", "Informe o nome do cliente ou desmarque 'Salvar como novo'."
            )
            return
        payload_cliente = {
            "nome_razao": nome,
            "tipo_pessoa": "PF",
        }
        telefone = limpo(self._telefone_cliente.valor())
        email = limpo(self._email_cliente.valor())
        if telefone:
            payload_cliente["telefone"] = telefone
        if email:
            payload_cliente["email"] = email

        self._btn_salvar.setEnabled(False)

        def criado(saida: dict) -> None:
            dado = saida.get("data", saida) if isinstance(saida, dict) else {}
            cid = dado.get("id")
            if cid is None:
                self._btn_salvar.setEnabled(True)
                QMessageBox.warning(self, "Cliente", "Não foi possível salvar o cliente.")
                return
            catalogos.invalidar("clientes")
            self._cliente._clientes[cid] = dado
            self._cliente.alterar_opcoes(
                [(cid, dado.get("nome_razao", nome))], self._cliente._clientes
            )
            self._cliente.definir(cid)
            self._salvar_novo_cliente.definir(False)
            self._cliente_flags[cid] = (
                bool(dado.get("pagamento_adiantado")),
                bool(dado.get("sinal")),
                dado.get("sinal_pct"),
            )
            super()._salvar()

        def erro(msg: str, _status: int | None = None) -> None:
            self._btn_salvar.setEnabled(True)
            QMessageBox.warning(self, "Cliente", msg)

        tarefas.rodar(
            lambda: self._api.criar("clientes", payload_cliente), criado, erro
        )

    def _cliente_da_os(self) -> tuple[int | None, str | None]:
        """Resolve cliente cadastrado ou nome avulso (Fase 2).

        - texto que casa com o rótulo da opção selecionada → `cliente_id`;
        - texto livre → `cliente_nome_avulso`;
        - campo vazio → (None, None) e a validação barra.

        A checagem do rótulo é essencial na edição: o combo pode manter um
        `currentData` antigo enquanto exibe um nome avulso. Sem ela, um PUT
        transformava silenciosamente o cliente avulso em outro cadastrado.
        """
        texto = self._cliente.texto
        if not texto:
            return None, None
        cid = self._cliente.valor()
        if cid is not None:
            indice = self._cliente.combo.currentIndex()
            rotulo = (
                str(self._cliente.combo.itemText(indice) or "").strip()
                if indice >= 0 else ""
            )
            if rotulo and rotulo.casefold() == texto.casefold():
                return cid, None
        return None, texto

    def _payload(self) -> dict:
        from decimal import ROUND_HALF_UP, Decimal

        cliente_id, cliente_avulso = self._cliente_da_os()
        valor_sinal = self._valor_sinal.valor()
        percentual = para_decimal(self._sinal_pct.valor())
        if valor_sinal is None and percentual:
            subtotal = Decimal("0")
            for item in self._itens.valor():
                qtd = para_decimal(item.get("quantidade")) or Decimal("0")
                unit = para_decimal(item.get("valor_unitario")) or Decimal("0")
                desconto_item = para_decimal(item.get("desconto")) or Decimal("0")
                subtotal += qtd * unit - desconto_item
            total = max(
                Decimal("0"),
                subtotal - (para_decimal(self._desconto.valor()) or Decimal("0")),
            )
            valor_sinal = (total * percentual / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return {
            "tipo": self.TIPO,
            "cliente_id": cliente_id,
            "cliente_nome_avulso": cliente_avulso,
            "vendedor_id": self._vendedor.valor(),
            "atendente_id": self._atendente.valor(),
            "data_previsao_entrega": (
                self._previsao.valor().date().isoformat() if self._previsao.valor() else None
            ),  # backend persiste data; UI permite hora (P1#9)
            "desconto": str(self._desconto.valor() or "0"),
            "forma_pagamento": self._forma.valor(),
            "valor_sinal": str(valor_sinal) if valor_sinal is not None else None,
            "forma_sinal": (self._forma_sinal.valor() if hasattr(self, "_forma_sinal") else None),
            "observacoes": limpo(self._obs.valor()),
            "pagamento_confirmado": self._pagamento_confirmado.valor(),
            "itens": self._itens.valor(),
        }

    # ------------------------------------------------------- ações de status

    def _acao_extra(self):
        """P0#1 (revisão PDV+Hist+OS): máx. 3 ações visíveis no rodapé.

        Avançar/Arte/Cancelar ficam em "Mais ações"; os botões reais são
        mantidos (ocultos, filhos do container) para compatibilidade com testes
        e com o bloqueio de modo leitura do PaginaCrud.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        avancar, self._btn_avancar = botao_com_atalho("Avançar Status", "F7")
        self._btn_avancar.clicked.connect(self._avancar_status)
        arte, self._btn_arte = botao_com_atalho("Arte", "F11")
        self._btn_arte.clicked.connect(self._abrir_arte)
        cancelar, self._btn_cancelar_os = botao_com_atalho(
            "Cancelar Projeto", "F8", "danger"
        )
        self._btn_cancelar_os.clicked.connect(self._cancelar_os)
        for oculto in (avancar, arte, cancelar):
            oculto.setVisible(False)
            layout.addWidget(oculto)

        btn_mais = QToolButton()
        btn_mais.setText("Mais ações")
        btn_mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn_mais.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(btn_mais)
        act_avancar = menu.addAction("Avançar status")
        act_avancar.triggered.connect(self._btn_avancar.click)
        act_arte = menu.addAction("Arte (M3)")
        act_arte.triggered.connect(self._btn_arte.click)
        menu.addSeparator()
        act_cancelar = menu.addAction("Cancelar projeto")
        act_cancelar.triggered.connect(self._btn_cancelar_os.click)
        btn_mais.setMenu(menu)
        layout.addWidget(btn_mais)
        self._btn_mais_acoes = btn_mais
        return [container]

    def _abrir_arte(self) -> None:
        """Diálogo de arte, prova e aprovação da O.S. selecionada (M3, §3.5)."""
        if self._editando_id is None:
            QMessageBox.information(
                self, "Arte", "Selecione uma O.S. na lista para gerenciar a arte."
            )
            return
        dialogo = DialogoArte(self, self._api, self._editando_id)
        dialogo.exec()

    def _selecionado_ou_aviso(self, titulo: str, msg: str) -> dict | None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(self, titulo, msg)
        return dado

    def _abrir_cotacoes_item(self, item: dict | None) -> None:
        """Abre o comparativo de fornecedores de um item (grade ou rodapé)."""
        if self._editando_id is None:
            QMessageBox.information(
                self, "Cotações", "Salve o orçamento antes de gerenciar cotações."
            )
            return
        if not item:
            QMessageBox.information(
                self, "Cotações", "Selecione um item na grade de itens."
            )
            return
        if (item.get("tipo") or "proprio") != "fornecedor":
            QMessageBox.information(
                self, "Cotações",
                "Cotações existem apenas para itens de fornecedor.\n"
                "Marque “Fornecedor” ao adicionar o item.",
            )
            return
        dialogo = DialogoCotacoes(self, self._api, self._editando_id, item)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.aprovado:
            self._itens.aplicar_cotacao(item.get("id"), dialogo.aprovado)
            if hasattr(self, "_sincronizar_acoes_form"):
                self._sincronizar_acoes_form(
                    getattr(self, "_em_formulario", False)
                )

    def _avancar_status(self) -> None:
        dado = self._selecionado_ou_aviso(
            "O.S.", "Selecione uma ordem de serviço na lista."
        )
        if not dado:
            return
        atual = dado.get("status")
        proximo = _PROXIMO_STATUS.get(atual)
        if proximo is None:
            QMessageBox.information(
                self, "O.S.", "Registro sem próxima etapa (entregue/cancelado)."
            )
            return
        # Atualiza o texto do botão para mostrar o destino
        self._btn_avancar.setText(f"Avançar para {_rotulo_status(proximo)}")
        item_id = dado["id"]
        self._btn_avancar.setEnabled(False)  # trava contra duplo PATCH
        tarefas.rodar(
            lambda: self._api.atualizar_status(item_id, proximo),
            on_ok=self._status_avancado,
            on_erro=self._status_avancado_erro,
        )

    def _status_avancado(self, _dado: dict) -> None:
        self._btn_avancar.setEnabled(True)
        self._btn_avancar.setText("Avançar Status")
        self.recarregar(self._busca.texto())

    def _status_avancado_erro(self, msg: str) -> None:
        self._btn_avancar.setEnabled(True)
        self._btn_avancar.setText("Avançar Status")
        self._erro_salvar(msg)

    def _cancelar_os(self) -> None:
        dado = self._selecionado_ou_aviso(
            self.ROTULO_PAGINA, "Selecione um registro na lista."
        )
        if not dado:
            return
        resposta = QMessageBox.question(
            self,
            "Cancelar Projeto",
            f"Cancelar permanentemente o projeto Nº {dado.get('numero')}?\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        item_id = dado["id"]
        tarefas.rodar(
            lambda: self._api.excluir(self.ENTIDADE, item_id),
            on_ok=lambda _out: self.recarregar(self._busca.texto()),
            on_erro=lambda msg: self._erro_salvar(msg),
        )


class PaginaOrcamento(PaginaOS):
    TIPO = "orcamento"
    ROTULO_PAGINA = "Orçamentos Gráficos & Simulações"
    ROTULO_NOVO = "Novo Orçamento"
    GRUPO_LISTA = "SIMULAÇÕES DE PREÇO"
    SECOES_RECOLHEIS = {"Prazos & Financeiro"}
    SECOES_ABERTAS_PADRAO = False  # progressivo: itens primeiro
    FILTROS = [
        ("", "Todos"),
        ("aberto", "Abertos"),
        ("convertido", "Convertidos"),
        ("cancelado", "Cancelados"),
    ]

    def _preencher_campos(self, dado: dict) -> None:
        super()._preencher_campos(dado)
        self._carregar_snapshots(dado.get("itens") or [])

    def _carregar_snapshots(self, itens: list[dict]) -> None:
        """A API de OS omite VF/CP: busca o snapshot nas rotas de cotação."""
        os_id = self._editando_id
        if os_id is None:
            return
        for item in itens:
            if (item.get("tipo") or "proprio") != "fornecedor" or not item.get("id"):
                continue
            item_id = item["id"]

            def ok(resposta, item_id=item_id) -> None:
                snapshot = (
                    resposta.get("selecionado")
                    if isinstance(resposta, dict) else None
                )
                if snapshot:
                    self._itens.aplicar_cotacao(item_id, snapshot)

            def _chamar(item_id=item_id) -> dict:
                resposta = self._api._cliente.get(
                    f"/v1/os/{os_id}/itens/{item_id}/cotacoes",
                    headers=self._api._headers(self._api.token),
                )
                return resposta.json()

            tarefas.rodar(_chamar, ok, lambda *_: None)

    def _acao_extra(self):
        """Orçamento: ações secundárias agrupadas em menu para caber no rodapé."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        converter, self._btn_converter = botao_com_atalho(
            "Converter em O.S.", "F9", "secondary"
        )
        self._btn_converter.clicked.connect(self._converter_em_os)
        self._widget_converter = converter
        layout.addWidget(converter)

        # Sem dica de atalho: F10 já é de "Salvar" no rodapé (botão_com_atalho
        # só desenha a dica, não instala QShortcut — a duplicata confundia).
        cotacoes, self._btn_cotacoes = botao_com_atalho("Cotações", "")
        self._btn_cotacoes.clicked.connect(self._abrir_cotacoes)
        self._widget_cotacoes = cotacoes
        cancelar, self._btn_cancelar_os = botao_com_atalho(
            "Cancelar Orçamento", "F8"
        )
        self._btn_cancelar_os.clicked.connect(self._cancelar_os)
        self._em_formulario = False
        for oculto in (cotacoes, cancelar):
            oculto.setVisible(False)
            layout.addWidget(oculto)

        btn_mais = _MenuAcima()
        btn_mais.setText("Mais ações")
        btn_mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn_mais.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(btn_mais)
        self._act_cot = menu.addAction("Cotações")
        self._act_cot.triggered.connect(self._btn_cotacoes.click)
        menu.addSeparator()
        self._act_cancelar = menu.addAction("Cancelar orçamento")
        self._act_cancelar.triggered.connect(self._btn_cancelar_os.click)
        self._act_cot.setVisible(False)  # na lista não há item selecionado na grade
        btn_mais.setMenu(menu)
        layout.addWidget(btn_mais)
        self._btn_mais_acoes = btn_mais
        return [container]

    def _conectar_campos(self) -> None:
        super()._conectar_campos()
        self._itens.selecao_alterada.connect(self._atualizar_botao_cotacoes)

    def _sincronizar_acoes_form(self, em_formulario: bool) -> None:
        """No formulário, Converter atua no rascunho e bloqueia sem cotação."""
        self._em_formulario = em_formulario
        self._act_cancelar.setVisible(not em_formulario)
        self._act_cot.setVisible(em_formulario)
        self._atualizar_botao_cotacoes()

    def _atualizar_botao_cotacoes(self) -> None:
        item = self._itens.item_selecionado
        fornecedor = bool(item) and (item.get("tipo") or "proprio") == "fornecedor"
        self._btn_cotacoes.setEnabled(fornecedor)
        self._widget_cotacoes.setVisible(self._em_formulario and fornecedor)
        self._atualizar_converter()

    def _atualizar_converter(self) -> None:
        botao = self._btn_converter
        if not self._em_formulario:
            botao.setEnabled(True)
            botao.setToolTip("Converter orçamento selecionado em ordem de serviço (F9)")
            return
        pendentes = len(self._itens.itens_pendentes())
        if pendentes:
            botao.setEnabled(False)
            botao.setToolTip(
                "Existem itens aguardando cotação. Resolva-os para converter."
            )
        elif self._editando_id is None:
            botao.setEnabled(False)
            botao.setToolTip("Salve o orçamento antes de converter em O.S.")
        else:
            botao.setEnabled(True)
            botao.setToolTip("Converter este orçamento em ordem de serviço (F9)")

    def _abrir_cotacoes(self) -> None:
        """Atalho do rodapé: usa o item selecionado na grade."""
        self._abrir_cotacoes_item(self._itens.item_selecionado)

    def _converter_em_os(self) -> None:
        if self._em_formulario:
            if self._editando_id is None:
                QMessageBox.information(
                    self, "Converter em O.S.", "Salve o orçamento antes de converter."
                )
                return
            if self._itens.itens_pendentes():
                QMessageBox.information(
                    self,
                    "Converter em O.S.",
                    "Existem itens aguardando cotação. Resolva-os para converter.",
                )
                return
            dado = {
                "id": self._editando_id,
                "numero": self._numero_registro(self._editando_id),
                "cliente_id": self._cliente.valor(),
            }
        else:
            dado = self._selecionado_ou_aviso(
                "Orçamentos", "Selecione um orçamento na lista."
            )
        if not dado:
            return
        exigencia = self._exigencia_do_cliente(dado.get("cliente_id"))
        confirmado = False
        if exigencia:
            resposta = QMessageBox.question(
                self,
                "Converter em O.S.",
                f"O cliente exige {exigencia}.\nConfirmar o recebimento e converter "
                f"o orçamento Nº {dado.get('numero')} em ordem de serviço?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
            confirmado = True
        else:
            resposta = QMessageBox.question(
                self,
                "Converter em O.S.",
                f"Converter o orçamento Nº {dado.get('numero')} em ordem de serviço?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        item_id = dado["id"]
        tarefas.rodar(
            lambda: self._api.acao(
                "os", item_id, "converter", {"pagamento_confirmado": confirmado}
            ),
            on_ok=self._convertido,
            on_erro=lambda msg: self._erro_salvar(msg),
        )

    def _convertido(self, dados: dict) -> None:
        self.recarregar(self._busca.texto())
        QMessageBox.information(
            self,
            "Ordem de Serviço gerada",
            f"Orçamento convertido na O.S. Nº {dados.get('numero')}.",
        )
