"""Módulo Movimento — Ordem de Serviço (mockup 3.1/3.2) e Orçamentos (3.3).

Ordem de serviço e orçamento vivem na mesma rota `/v1/os`, diferenciados por
`tipo`. A página é a mesma base `PaginaCrud` com `TIPO` fixo; a subclasse de
orçamento troca rótulos e adiciona a ação de conversão (`POST /{id}/converter`).
O avanço de status usa `PATCH /{id}/status` e o cancelamento `DELETE /{id}`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
    CampoCombo,
    CampoDataHora,
    CampoTexto,
    CampoValor,
    data_iso,
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


# ------------------------------------------------------- diálogo de cotações

_COTACAO_CHAVES = ["fornecedor_nome", "vf", "prazo_dias", "validade", "selecionada"]
_COTACAO_ROTULOS = ["Fornecedor", "VF", "Prazo (dias)", "Validade", "✓"]


class DialogoCotacoes(QDialog):
    """Comparativo + lançamento + seleção de cotações (M1, §3.2.2/§3.2.3).

    Três zonas:
    - **Comparativo** em tabela (VF/prazo/validade por linha, ✓ na selecionada);
    - **Formulário** de lançamento (fornecedor, VF, prazo, validade, observações,
      marcar como selecionada);
    - **Bloco de cálculo** com VF/CP/VO quando o servidor os manda (Admin/Gerente).

    VF/snapshot são **omitidos** pelo servidor para Operador — o diálogo mostra
    "(restrito)" em vez do valor (a chave nem existe na resposta, §3.2.3).
    """

    def __init__(self, parent, api, os_id: int, item: dict) -> None:
        super().__init__(parent)
        self._api = api
        self._os_id = os_id
        self._item = item
        self._cotacoes: list[dict] = []
        self._pode_ver_custo: bool = False

        self.setWindowTitle("Cotações de Fornecedor")
        self.setMinimumSize(620, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        descricao = item.get("descricao_avulsa") or "item selecionado"
        titulo = QLabel(f"Item: {descricao}")
        titulo.setObjectName("subtitulo")
        root.addWidget(titulo)

        # --- comparativo
        self._lbl_estado = QLabel("Carregando…")
        estado_muted(self._lbl_estado)
        root.addWidget(self._lbl_estado)

        self._tabela = TabelaDensa(_COTACAO_CHAVES, _COTACAO_ROTULOS)
        self._tabela.setMinimumHeight(120)
        root.addWidget(self._tabela, 1)

        # --- snapshot do cálculo (visível só com permissão)
        self._lbl_snapshot = QLabel("")
        self._lbl_snapshot.setWordWrap(True)
        estado_muted(self._lbl_snapshot)
        root.addWidget(self._lbl_snapshot)

        # --- formulário de lançamento
        card = QWidget()
        card.setObjectName("card")
        form = QGridLayout(card)
        form.setContentsMargins(16, 12, 16, 12)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        rotulo_form = QLabel("Lançar cotação")
        rotulo_form.setObjectName("secaoForm")
        form.addWidget(rotulo_form, 0, 0, 1, 2)

        self._campo_fornecedor = CampoCombo("Fornecedor", [])
        self._campo_vf = CampoValor("VF (valor do fornecedor)")
        self._campo_prazo = CampoTexto("Prazo (dias)", maximo=4)
        self._campo_validade = CampoData("Validade da cotação")
        self._campo_obs = CampoTexto("Observações", maximo=200)
        self._check_selecionar = CampoCheck("Selecionar esta cotação")

        form.addWidget(self._campo_fornecedor.rotulo_widget, 1, 0)
        form.addWidget(self._campo_fornecedor.widget, 1, 0)
        form.addWidget(self._campo_vf.rotulo_widget, 1, 1)
        form.addWidget(self._campo_vf.widget, 1, 1)
        form.addWidget(self._campo_prazo.rotulo_widget, 2, 0)
        form.addWidget(self._campo_prazo.widget, 2, 0)
        form.addWidget(self._campo_validade.rotulo_widget, 2, 1)
        form.addWidget(self._campo_validade.widget, 2, 1)
        form.addWidget(self._campo_obs.rotulo_widget, 3, 0)
        form.addWidget(self._campo_obs.widget, 3, 0)
        form.addWidget(self._check_selecionar.widget, 3, 1)
        root.addWidget(card)

        # --- botões
        botoes = QHBoxLayout()
        botoes.setSpacing(8)
        self._btn_lancar = QPushButton("Lançar cotação")
        estado_primario(self._btn_lancar)
        self._btn_lancar.clicked.connect(self._lancar)
        botoes.addWidget(self._btn_lancar)

        self._btn_selecionar = QPushButton("Selecionar marcada")
        self._btn_selecionar.clicked.connect(self._selecionar)
        botoes.addWidget(self._btn_selecionar)

        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.accept)
        botoes.addStretch(1)
        botoes.addWidget(fechar)
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
        self._campo_fornecedor.alterar_opcoes(
            [(r["id"], r["nome_razao"]) for r in saida.get("data", [])]
        )

    def _carregar(self) -> None:
        item_id = self._item.get("id")
        if not item_id:
            self._lbl_estado.setText("Salve o orçamento antes de gerenciar cotações.")
            self._tabela.setEnabled(False)
            self._btn_lancar.setEnabled(False)
            self._btn_selecionar.setEnabled(False)
            return
        os_id = self._os_id

        def _chamar():
            """Lê a resposta COMPLETA (data/estado/selecionado)."""
            resp = self._api._cliente.get(
                f"/v1/os/{os_id}/itens/{item_id}/cotacoes",
                headers=self._api._headers(self._api.token),
            )
            return resp.json()

        tarefas.rodar(
            _chamar,
            on_ok=self._preencher,
            on_erro=lambda msg: self._lbl_estado.setText(f"Erro ao carregar: {msg}"),
        )

    def _preencher(self, resposta: dict) -> None:
        self._cotacoes = resposta.get("data") or []
        selecionado = resposta.get("selecionado") or {}
        estado = resposta.get("estado_cotacao")
        self._pode_ver_custo = bool(selecionado)  # servidor mandou o snapshot

        # estado do item
        if estado == "cotado":
            self._lbl_estado.setText("✓ Item cotado — cotação selecionada define o valor.")
            estado_sucesso(self._lbl_estado)
        elif estado == "aguardando":
            self._lbl_estado.setText("⚠ Item aguardando cotação — selecione uma para aprovar.")
            estado_atencao(self._lbl_estado)
        else:
            self._lbl_estado.setText("")
            estado_muted(self._lbl_estado)
        aplicar_estilo(self._lbl_estado)

        # tabela
        linhas = []
        for c in self._cotacoes:
            vf = c.get("vf")
            linhas.append({
                "fornecedor_nome": c.get("fornecedor_nome", "?"),
                "vf": f"R$ {vf}" if vf is not None else "(restrito)",
                "prazo_dias": str(c.get("prazo_dias") or "—"),
                "validade": str(c.get("validade") or "—"),
                "selecionada": "✓" if c.get("selecionada") else "",
            })
        self._tabela.preencher(linhas)
        self._tabela.setEnabled(True)

        # snapshot
        if selecionado:
            self._lbl_snapshot.setText(
                f"VF: R$ {selecionado.get('vf', '?')}  ·  "
                f"CP: R$ {selecionado.get('cp', '?')} (interno)  ·  "
                f"VO: R$ {selecionado.get('vo', '?')}  ← valor do item"
            )
            estado_muted(self._lbl_snapshot)
        else:
            self._lbl_snapshot.setText("")
            estado_muted(self._lbl_snapshot)
        aplicar_estilo(self._lbl_snapshot)

        self._btn_selecionar.setEnabled(bool(self._cotacoes))

    # ------------------------------------------------------------- ações

    def _lancar(self) -> None:
        fornecedor_id = self._campo_fornecedor.valor()
        if not fornecedor_id:
            QMessageBox.warning(self, "Cotação", "Selecione o fornecedor.")
            return
        vf = self._campo_vf.valor()
        if vf is None or vf <= 0:
            QMessageBox.warning(self, "Cotação", "Informe o VF (valor do fornecedor).")
            return

        corpo = {
            "fornecedor_id": fornecedor_id,
            "vf": str(vf),
            "prazo_dias": int(self._campo_prazo.valor() or 0) or None,
            "observacoes": limpo(self._campo_obs.valor()),
            "selecionada": self._check_selecionar.valor(),
        }
        validade = self._campo_validade.valor()
        if validade:
            corpo["validade"] = data_iso(validade)

        item_id = self._item.get("id")
        os_id = self._os_id
        self._btn_lancar.setEnabled(False)
        self._btn_lancar.setText("Lançando…")

        def ok(_resultado) -> None:
            self._btn_lancar.setEnabled(True)
            self._btn_lancar.setText("Lançar cotação")
            self._campo_vf.definir(None)
            self._campo_prazo.definir("")
            self._campo_obs.definir(None)
            self._check_selecionar.definir(False)
            self._carregar()

        def erro(msg: str) -> None:
            self._btn_lancar.setEnabled(True)
            self._btn_lancar.setText("Lançar cotação")
            QMessageBox.critical(self, "Cotação", msg)

        tarefas.rodar(
            lambda: self._api.lancar_cotacao(os_id, item_id, corpo),
            on_ok=ok,
            on_erro=erro,
        )

    def _selecionar(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._cotacoes):
            QMessageBox.information(self, "Cotação", "Selecione uma cotação na tabela.")
            return
        cotacao = self._cotacoes[linha]
        cotacao_id = cotacao.get("id")
        if not cotacao_id:
            return
        if cotacao.get("selecionada"):
            QMessageBox.information(self, "Cotação", "Esta cotação já está selecionada.")
            return

        item_id = self._item.get("id")
        os_id = self._os_id
        self._btn_selecionar.setEnabled(False)
        self._btn_selecionar.setText("Selecionando…")

        def ok(_resultado) -> None:
            self._btn_selecionar.setEnabled(True)
            self._btn_selecionar.setText("Selecionar marcada")
            self._carregar()

        def erro(msg: str) -> None:
            self._btn_selecionar.setEnabled(True)
            self._btn_selecionar.setText("Selecionar marcada")
            QMessageBox.critical(self, "Cotação", msg)

        tarefas.rodar(
            lambda: self._api.selecionar_cotacao(os_id, item_id, cotacao_id),
            on_ok=ok,
            on_erro=erro,
        )


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
        if getattr(self, "_filtros_widget", None) is not None and self._filtros_widget.layout() is not None:
            self._filtros_widget.layout().addWidget(self._lbl_contadores_os)
        self._carregar_clientes_flags()
        self._carregar_funcionarios()
        self._atualizar_contadores_os()
        # Consistência de ação principal no fluxo de OS
        if hasattr(self, "_btn_salvar"):
            self._btn_salvar.setToolTip("Salvar ordem de serviço (F10)")

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._iniciar_condicao_pagamento()  # flags de pagamento por cliente
        self._cliente = CampoCombo("Cliente", []).obrigatorio()
        self._vendedor = CampoCombo("Vendedor", [])
        self._atendente = CampoCombo("Atendente", [])
        # P1#9: data + hora (backend persiste data; hora melhora UX de planejamento)
        self._previsao = CampoDataHora("Previsão de Entrega", obrigatorio=False)
        self._forma = CampoCombo("Forma de Pagamento", FORMAS_PAGAMENTO)
        self._valor_sinal = CampoValor("Sinal (valor)")
        self._forma_sinal = CampoCombo("Forma do Sinal", FORMAS_PAGAMENTO)
        self._desconto = CampoValor("Desconto")
        self._obs = CampoArea("Observações", linhas=2)
        self._pagamento_confirmado = CampoCheck("Pagamento já recebido")
        self._itens = GradeItens("", api=self._api)
        # P0#2 (refino): em tela cheia, a grade de itens precisa de área útil
        # sem comprimir o restante do formulário em 1024x768.
        self._itens.setMinimumHeight(260)
        self._itens._tabela.setMinimumHeight(170)

        # P1#11: combos pesquisáveis (digitação filtra opções).
        for campo, placeholder in (
            (self._cliente, "Buscar/selecionar cliente"),
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
        cliente_widget = QWidget()
        linha_cli = QHBoxLayout(cliente_widget)
        linha_cli.setContentsMargins(0, 0, 0, 0)
        linha_cli.setSpacing(6)
        linha_cli.addWidget(self._cliente.widget, 1)
        linha_cli.addWidget(self._btn_novo_cliente)

        class _CampoClienteWrap:
            largo = False
            def __init__(self, campo, widget):
                self._campo = campo
                self.rotulo_widget = campo.rotulo_widget
                self.widget = widget
            def valor(self):
                return self._campo.valor()
            def definir(self, v):
                return self._campo.definir(v)
            def habilitar(self, ligado: bool):
                self._campo.habilitar(ligado)
                self.widget.setEnabled(ligado)
            def obrigatorio(self):
                self._campo.obrigatorio()
                return self

        self._cliente_campo = _CampoClienteWrap(self._cliente, cliente_widget)

        return [
            ("Cliente & Equipe", [self._cliente_campo, self._vendedor, self._atendente]),
            (
                "Prazos & Financeiro",
                [
                    self._previsao,
                    self._forma,
                    self._valor_sinal,
                    self._forma_sinal,
                    self._desconto,
                    self._obs,
                    self._pagamento_confirmado,
                ],
            ),
            ("Itens", [self._itens]),
        ]

    def _conectar_campos(self) -> None:
        self._cliente.widget.currentIndexChanged.connect(self._ao_mudar_cliente_os)
        self._desconto.edicao.textChanged.connect(self._atualizar_totais_os)
        if hasattr(self._valor_sinal, "edicao"):
            self._valor_sinal.edicao.textChanged.connect(self._atualizar_totais_os)
        self._itens.alterado.connect(self._atualizar_totais_os)

    def _ao_mudar_cliente_os(self) -> None:
        self._cliente_mudou()
        self._atualizar_totais_os()

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
        self._lbl_totais_os = QLabel("Itens R$ 0,00 · Desconto R$ 0,00 · Total R$ 0,00")
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
        for item in self._itens.valor():
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
            f"Itens {formatar_moeda(str(subtotal))} · "
            f"Desconto {formatar_moeda(str(desconto))} · "
            f"Total {formatar_moeda(str(total))}{saldo_txt}"
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
        try:
            usuario = (self._api.usuario() or {}) if hasattr(self._api, "usuario") else {}
        except Exception:
            usuario = {}
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
        if chave == "status":
            return str(dado.get("status", "")).upper()
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
        self._cliente.definir(dado.get("cliente_id"))
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
        self._obs.definir(dado.get("observacoes"))
        self._pagamento_confirmado.definir(False)
        self._itens.definir(dado.get("itens") or [])
        self._atualizar_totais_os()

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._cliente.valor():
            return ("Informe o cliente.", self._cliente)
        if not self._itens.valor():
            return ("Adicione ao menos um item.", self._itens.widget)
        if self._editando_id is None and self.TIPO == "os":
            exigencia = self._exigencia_pendente()
            if exigencia:
                return (
                    f"O cliente exige {exigencia}. Marque 'Pagamento já recebido' "
                    "para lançar a O.S.",
                    self._pagamento_confirmado,
                )
        return None

    def _payload(self) -> dict:
        return {
            "tipo": self.TIPO,
            "cliente_id": self._cliente.valor(),
            "vendedor_id": self._vendedor.valor(),
            "atendente_id": self._atendente.valor(),
            "data_previsao_entrega": (
                self._previsao.valor().date().isoformat() if self._previsao.valor() else None
            ),  # backend persiste data; UI permite hora (P1#9)
            "desconto": str(self._desconto.valor() or "0"),
            "forma_pagamento": self._forma.valor(),
            "valor_sinal": (str(self._valor_sinal.valor()) if hasattr(self, "_valor_sinal") and self._valor_sinal.valor() is not None else None),
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
    FILTROS = [
        ("", "Todos"),
        ("aberto", "Abertos"),
        ("convertido", "Convertidos"),
        ("cancelado", "Cancelados"),
    ]

    def _acao_extra(self):
        """Orçamento: ações secundárias agrupadas em menu para caber no rodapé."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        converter, self._btn_converter = botao_com_atalho(
            "Converter em O.S.", "F9", "primary"
        )
        self._btn_converter.clicked.connect(self._converter_em_os)
        layout.addWidget(converter)

        cotacoes, self._btn_cotacoes = botao_com_atalho("Cotações", "F10")
        self._btn_cotacoes.clicked.connect(self._abrir_cotacoes)
        cancelar, self._btn_cancelar_os = botao_com_atalho(
            "Cancelar Orçamento", "F8"
        )
        self._btn_cancelar_os.clicked.connect(self._cancelar_os)
        for oculto in (cotacoes, cancelar):
            oculto.setVisible(False)
            layout.addWidget(oculto)

        btn_mais = QToolButton()
        btn_mais.setText("Mais ações")
        btn_mais.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn_mais.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(btn_mais)
        act_cot = menu.addAction("Cotações")
        act_cot.triggered.connect(self._btn_cotacoes.click)
        menu.addSeparator()
        act_cancelar = menu.addAction("Cancelar orçamento")
        act_cancelar.triggered.connect(self._btn_cancelar_os.click)
        btn_mais.setMenu(menu)
        layout.addWidget(btn_mais)
        self._btn_mais_acoes = btn_mais
        return [container]

    def _abrir_cotacoes(self) -> None:
        """Diálogo de cotações para o item de fornecedor selecionado na grade."""
        if self._editando_id is None:
            QMessageBox.information(
                self, "Cotações", "Salve o orçamento antes de gerenciar cotações."
            )
            return
        item = self._itens.item_selecionado
        if not item:
            QMessageBox.information(
                self, "Cotações", "Selecione um item na grade de itens."
            )
            return
        if (item.get("tipo") or "proprio") != "fornecedor":
            QMessageBox.information(
                self,
                "Cotações",
                "Cotações existem apenas para itens de fornecedor.\n"
                "Marque “Fornecedor” ao adicionar o item.",
            )
            return
        dialogo = DialogoCotacoes(self, self._api, self._editando_id, item)
        dialogo.exec()

    def _converter_em_os(self) -> None:
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
