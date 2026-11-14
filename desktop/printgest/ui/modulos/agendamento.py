"""Módulo Agendamento (PRD §1.3 / telas_e_fluxos §1.3 — Calendário/Lista).

Compromissos de **produção** e **entrega** sobre `/v1/agendamento` (tabela
`agendamento`, já no `schema.sql`). Duas visões:

  - **Calendário** (padrão): grade mensal com os compromissos do mês; clicar
    num dia lista os compromissos daquele dia.
  - **Lista**: grade densa do mês, com filtros por tipo/status e paginação.

Clicar num compromisso abre a **ficha** (criar/editar) no painel lateral. RBAC:
operador+ (herdado do menu interno `agendamento`). Escrita bloqueada em modo
leitura (a API responde 423).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from printgest.core.api import Api
import printgest.core.tarefas as tarefas
from printgest.ui.busca import CampoBusca
from printgest.ui.formulario import (
    CampoArea,
    CampoCombo,
    CampoDataHora,
    CampoTexto,
    dispor_campos,
    formatar_data_iso,
    grade_campos,
    limpo,
    rotulo_secao,
)
from printgest.ui.paginador import Paginador
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import (
    ElideLabel,
    FlowLayout,
    aplicar_estilo,
    badge,
    botao_com_atalho,
    estado_sucesso,
    estado_erro,
    estado_muted,
)

_TIPOS = [("producao", "Produção"), ("entrega", "Entrega")]
_STATUS = [
    ("agendado", "Agendado"),
    ("concluido", "Concluído"),
    ("cancelado", "Cancelado"),
]
# Cores do chip de compromisso por tipo (produção=primário, entrega=sucesso).
_TIPO_CLASSE = {"producao": "primary", "entrega": "success"}
_STATUS_CLASSE = {"agendado": "", "concluido": "muted", "cancelado": "erro"}

_CHAVES = ["data_hora_inicio", "hora", "tipo", "titulo", "ordem_servico", "status"]
_COLUNAS = ["Data", "Hora", "Tipo", "Título", "O.S.", "Status"]
_PESOS = [2, 1, 2, 6, 3, 2]

_DIAS_SEMANA = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


# ============================================================== célula do mês


class CelulaDia(QWidget):
    """Uma célula do calendário: número do dia + até 2 chips de compromisso."""

    clicada = Signal(QDate)
    compromisso_clicado = Signal(int)

    def __init__(self, dia: QDate, no_mes: bool, parent=None) -> None:
        super().__init__(parent)
        self._dia = dia
        self._no_mes = no_mes
        self.setProperty("celulaDia", "true")
        self.setProperty("foraDoMes", no_mes)
        aplicar_estilo(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)

        topo = QWidget()
        linha = QHBoxLayout(topo)
        linha.setContentsMargins(0, 0, 0, 0)
        self._numero = QLabel(str(dia.day()))
        if no_mes:
            estado_muted(self._numero)
        linha.addWidget(self._numero, 1)
        layout.addWidget(topo)

        self._chips = QWidget()
        self._chips_layout = QVBoxLayout(self._chips)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(1)
        layout.addWidget(self._chips, 1)

    @property
    def dia(self) -> QDate:
        return self._dia

    def preencher(self, compromissos: list[dict]) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            antigo = item.widget()
            if antigo is not None:
                antigo.setParent(None)
                antigo.deleteLater()
        for dado in compromissos[:2]:
            self._chips_layout.addWidget(self._chip(dado))
        if len(compromissos) > 2:
            mais = QLabel(f"+{len(compromissos) - 2} mais")
            estado_muted(mais)
            self._chips_layout.addWidget(mais)

    def _chip(self, dado: dict) -> QPushButton:
        botao = QPushButton(dado.get("titulo", ""))
        botao.setFlat(True)
        botao.setProperty("chipEvento", "true")
        botao.setProperty("chipTipo", _TIPO_CLASSE.get(dado.get("tipo"), ""))
        aplicar_estilo(botao)
        inicio = dado.get("data_hora_inicio") or ""
        hora = inicio[11:16] if len(inicio) >= 16 else ""
        os_num = dado.get("ordem_servico_numero")
        detalhe = f"O.S. Nº {os_num}" if os_num else "Sem O.S."
        botao.setToolTip(f"{hora} · {dado.get('titulo', '')}\n{detalhe}")
        botao.clicked.connect(lambda _=False, i=dado.get("id"): self.compromisso_clicado.emit(i))
        return botao

    def atualizar_estado(self, selecionada: bool) -> None:
        self.setProperty("selecionada", selecionada)
        self.setProperty("hoje", self._dia == QDate.currentDate())
        aplicar_estilo(self)

    def mousePressEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicada.emit(self._dia)
        super().mousePressEvent(evento)


# =============================================================== calendário mensal


class CalendarioMes(QWidget):
    """Grade de 6 semanas (42 células) para um mês, com navegação."""

    dia_clicado = Signal(QDate)
    compromisso_clicado = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mes = QDate.currentDate().addDays(-QDate.currentDate().day() + 1)
        self._dia_selecionado = QDate.currentDate()
        self._celulas: dict[int, CelulaDia] = {}

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(6)
        raiz.addWidget(self._navegacao())

        self._grade = QGridLayout()
        self._grade.setContentsMargins(0, 0, 0, 0)
        self._grade.setHorizontalSpacing(2)
        self._grade.setVerticalSpacing(2)
        for col, rotulo in enumerate(_DIAS_SEMANA):
            cab = QLabel(rotulo)
            estado_muted(cab)
            cab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grade.addWidget(cab, 0, col)
        for i in range(42):
            linha, col = divmod(i, 7)
            dia = self._inicio_mes().addDays(i)
            celula = CelulaDia(dia, dia.month() != self._mes.month())
            celula.clicada.connect(self._dia_clicado)
            celula.compromisso_clicado.connect(self.compromisso_clicado)
            self._grade.addWidget(celula, linha + 1, col)
            self._celulas[i] = celula
        raiz.addLayout(self._grade)
        self._atualizar_rotulo()

    # -------------------------------------------------------------- construção

    def _navegacao(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        self._anterior = QPushButton("‹")
        self._anterior.setProperty("navCalendario", "true")
        self._anterior.setFixedWidth(28)
        self._anterior.clicked.connect(lambda: self._mudar_mes(-1))
        self._proximo = QPushButton("›")
        self._proximo.setProperty("navCalendario", "true")
        self._proximo.setFixedWidth(28)
        self._proximo.clicked.connect(lambda: self._mudar_mes(+1))
        self._rotulo = QLabel("")
        estado_muted(self._rotulo)
        self._rotulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rotulo.setMinimumWidth(0)
        hoje = QPushButton("Hoje")
        hoje.setProperty("navCalendario", "true")
        hoje.setFixedWidth(50)
        hoje.clicked.connect(self._ir_para_hoje)
        linha.addWidget(self._anterior)
        linha.addWidget(self._rotulo, 1)
        linha.addWidget(hoje)
        linha.addWidget(self._proximo)
        return caixa

    def _inicio_mes(self) -> QDate:
        primeiro = QDate(self._mes.year(), self._mes.month(), 1)
        # Semana começa na segunda (dayOfWeek: seg=1 … dom=7).
        return primeiro.addDays(-primeiro.dayOfWeek() + 1)

    # ------------------------------------------------------------------ eventos

    @property
    def mes(self) -> QDate:
        return self._mes

    def _dia_clicado(self, dia: QDate) -> None:
        self._dia_selecionado = dia
        self._atualizar_selecao()
        self.dia_clicado.emit(dia)

    def _atualizar_selecao(self) -> None:
        for celula in self._celulas.values():
            celula.atualizar_estado(celula.dia == self._dia_selecionado)

    def _ir_para_hoje(self) -> None:
        hoje = QDate.currentDate()
        self._mes = hoje.addDays(-hoje.day() + 1)
        self._atualizar_rotulo()
        self.recriar_grade()
        self._dia_clicado(hoje)

    def _mudar_mes(self, delta: int) -> None:
        self._mes = self._mes.addMonths(delta)
        self._atualizar_rotulo()
        self.recriar_grade()

    def _texto_mes(self) -> str:
        return f"{_MESES[self._mes.month() - 1]} de {self._mes.year()}"

    def _atualizar_rotulo(self) -> None:
        self._rotulo.setText(self._texto_mes())

    def recriar_grade(self) -> None:
        """Reconstrói as células após mudar o mês."""
        inicio = self._inicio_mes()
        for celula in self._celulas.values():
            self._grade.removeWidget(celula)
            celula.deleteLater()
        self._celulas.clear()
        for i in range(42):
            dia = inicio.addDays(i)
            nova = CelulaDia(dia, dia.month() != self._mes.month())
            nova.clicada.connect(self._dia_clicado)
            nova.compromisso_clicado.connect(self.compromisso_clicado)
            self._grade.addWidget(nova, i // 7 + 1, i % 7)
            self._celulas[i] = nova
        self._atualizar_selecao()

    def preencher(self, compromissos: list[dict]) -> None:
        por_dia: dict[str, list[dict]] = {}
        for dado in compromissos:
            inicio = dado.get("data_hora_inicio") or ""
            try:
                dia = date.fromisoformat(inicio[:10])
            except ValueError:
                continue
            por_dia.setdefault(dia.isoformat(), []).append(dado)
        for celula in self._celulas.values():
            chave = celula.dia.toString("yyyy-MM-dd")
            celula.preencher(por_dia.get(chave, []))


# ======================================================================= página


class PaginaAgendamento(QWidget):
    """Agendamento — Calendário (padrão) e Lista, com ficha lateral."""

    ROTULO_PAGINA = "Agendamento"
    ROTULO_NOVO = "Novo Agendamento"
    LUGAR_BUSCA = "Buscar por título ou O.S...."
    VAZIO = "Nenhum compromisso no período."

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._mes = QDate.currentDate().addDays(-QDate.currentDate().day() + 1)
        self._dia_selecionado = QDate.currentDate()
        self._filtro_tipo = ""
        self._filtro_status = ""
        self._editando_id: int | None = None
        self._ultimos: list[dict] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(10)
        raiz.addWidget(self._barra_titulo())
        raiz.addWidget(self._barra_busca())

        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)

        # Esquerda: calendário ou lista (trocados em vez de empilhados).
        self._calendario = CalendarioMes()
        self._calendario.dia_clicado.connect(self._dia_calendario_clicado)
        self._calendario.compromisso_clicado.connect(self._abrir_compromisso)
        self._painel_dia = self._painel_dia()
        caixa_cal = QWidget()
        caixa_cal.setObjectName("card")
        col_cal = QVBoxLayout(caixa_cal)
        col_cal.setContentsMargins(0, 8, 0, 0)
        col_cal.setSpacing(8)
        col_cal.addWidget(self._calendario, 0)
        col_cal.addWidget(self._painel_dia, 1)

        self._tabela = TabelaDensa(_CHAVES, _COLUNAS, _PESOS)
        self._tabela.estado_vazio(self.VAZIO)
        self._tabela.formata = self._formatar_texto
        self._tabela.itemSelectionChanged.connect(self._selecao_mudou)
        self._paginador = Paginador()
        self._paginador.mudou.connect(lambda offset: self._carregar_lista(offset))
        caixa_lista = QWidget()
        caixa_lista.setObjectName("card")
        col_lista = QVBoxLayout(caixa_lista)
        col_lista.setContentsMargins(0, 8, 0, 0)
        col_lista.setSpacing(0)
        col_lista.addWidget(self._tabela, 1)
        pag_linha = QWidget()
        pl = QHBoxLayout(pag_linha)
        pl.setContentsMargins(14, 8, 14, 8)
        pl.addWidget(self._paginador)
        col_lista.addWidget(pag_linha)

        divisor.addWidget(caixa_cal)
        divisor.addWidget(caixa_lista)
        divisor.addWidget(self._painel_form())
        divisor.setStretchFactor(0, 1)
        divisor.setStretchFactor(1, 0)
        divisor.setStretchFactor(2, 0)
        divisor.setSizes([560, 460, 460])
        raiz.addWidget(divisor, 1)

        self._visao_atual = 0
        self._mostrar_visao(0)

        QShortcut(QKeySequence("F6"), self, self._novo)
        QShortcut(QKeySequence("F10"), self, self._salvar)
        QShortcut(QKeySequence("Esc"), self, self._cancelar)

        self._carregar_os()
        self._carregar_periodo()
        self._carregar_lista()

    # -------------------------------------------------------------- construção

    def _barra_titulo(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        titulo = ElideLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        linha.addWidget(titulo, 1)

        self._btn_calendario = QPushButton("Calendário")
        self._btn_lista = QPushButton("Lista")
        for botao in (self._btn_calendario, self._btn_lista):
            botao.setObjectName("chaveRapida")
            botao.setCheckable(True)
            linha.addWidget(botao)
        self._btn_calendario.setChecked(True)
        self._btn_calendario.clicked.connect(lambda: self._mostrar_visao(0))
        self._btn_lista.clicked.connect(lambda: self._mostrar_visao(1))

        novo, self._btn_novo = botao_com_atalho(self.ROTULO_NOVO, "F6", "primary")
        linha.addWidget(novo)
        self._btn_novo.clicked.connect(self._novo)
        return caixa

    def _barra_busca(self) -> QWidget:
        caixa = QWidget()
        layout = QHBoxLayout(caixa)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._busca = CampoBusca(self.LUGAR_BUSCA)
        self._busca.buscado.connect(lambda q: self._carregar_lista())
        layout.addWidget(self._busca, 1)

        self._filtros_widget = QWidget()
        fluxo = FlowLayout(self._filtros_widget, espaco_h=8, espaco_v=8)
        self._btn_tipos = {}
        for valor, rotulo in [("", "Todos os tipos")] + _TIPOS:
            botao = QPushButton(rotulo)
            botao.setCheckable(True)
            botao.setObjectName("chaveRapida")
            if valor == "":
                botao.setChecked(True)
            botao.clicked.connect(lambda _=False, v=valor: self._filtrar_tipo(v))
            self._btn_tipos[valor] = botao
            fluxo.addWidget(botao)
        self._btn_status = {}
        for valor, rotulo in [("", "Todos os status")] + _STATUS:
            botao = QPushButton(rotulo)
            botao.setCheckable(True)
            botao.setObjectName("chaveRapida")
            if valor == "":
                botao.setChecked(True)
            botao.clicked.connect(lambda _=False, v=valor: self._filtrar_status(v))
            self._btn_status[valor] = botao
            fluxo.addWidget(botao)
        layout.addWidget(self._filtros_widget, 0)
        return caixa

    def _painel_dia(self) -> QWidget:
        caixa = QWidget()
        aplicar_estilo(caixa)
        self._rotulo_dia = QLabel("")
        estado_muted(self._rotulo_dia)
        layout = QVBoxLayout(caixa)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._rotulo_dia)
        self._lista_dia = QWidget()
        self._lista_dia_layout = QVBoxLayout(self._lista_dia)
        self._lista_dia_layout.setContentsMargins(0, 0, 0, 0)
        self._lista_dia_layout.setSpacing(4)
        layout.addWidget(self._lista_dia, 1)
        return caixa

    # ------------------------------------------------------------------- visões

    def _mostrar_visao(self, indice: int) -> None:
        divisor = self.layout().itemAt(2).widget()
        cal, lista = divisor.widget(0), divisor.widget(1)
        alvo = cal if indice == 0 else lista
        outro = lista if indice == 0 else cal
        outro.hide()
        alvo.show()
        self._visao_atual = indice
        self._btn_calendario.setChecked(indice == 0)
        self._btn_lista.setChecked(indice == 1)
        self._filtros_widget.setVisible(indice == 1)
        self._busca.setVisible(indice == 1)
        if indice == 0:
            self._carregar_periodo()
        else:
            self._carregar_lista()

    # --------------------------------------------------------------- calendário

    def _dia_calendario_clicado(self, dia: QDate) -> None:
        self._dia_selecionado = dia
        self._atualizar_painel_dia()

    def _atualizar_painel_dia(self) -> None:
        dia = self._dia_selecionado
        self._rotulo_dia.setText(
            f"Compromissos de {dia.day():02d}/{dia.month():02d}/{dia.year()}"
        )
        while self._lista_dia_layout.count():
            item = self._lista_dia_layout.takeAt(0)
            antigo = item.widget()
            if antigo is not None:
                antigo.setParent(None)
                antigo.deleteLater()
        # Compromissos do dia vêm do último carregamento do mês.
        inicio = dia.toString("yyyy-MM-dd")
        compromissos = [
            c for c in self._ultimos
            if (c.get("data_hora_inicio") or "").startswith(inicio)
        ]
        compromissos.sort(key=lambda c: c.get("data_hora_inicio") or "")
        if not compromissos:
            vazio = QLabel("Neste dia não há compromissos.")
            estado_muted(vazio)
            self._lista_dia_layout.addWidget(vazio)
        for dado in compromissos:
            self._lista_dia_layout.addWidget(self._cartao_dia(dado))

    def _cartao_dia(self, dado: dict) -> QPushButton:
        os_num = dado.get("ordem_servico_numero")
        hora = (dado.get("data_hora_inicio") or "")[11:16]
        texto = f"{hora}  {dado.get('titulo', '')}"
        if os_num:
            texto += f"  ·  O.S. Nº {os_num}"
        botao = QPushButton(texto)
        botao.setProperty("chipEvento", "true")
        botao.setProperty("chipTipo", _TIPO_CLASSE.get(dado.get("tipo"), ""))
        aplicar_estilo(botao)
        botao.clicked.connect(lambda _=False, i=dado.get("id"): self._abrir_compromisso(i))
        return botao

    # -------------------------------------------------------------------- lista

    def _filtrar_tipo(self, valor: str) -> None:
        self._filtro_tipo = valor
        for v, botao in self._btn_tipos.items():
            botao.setChecked(v == valor)
        self._carregar_lista()

    def _filtrar_status(self, valor: str) -> None:
        self._filtro_status = valor
        for v, botao in self._btn_status.items():
            botao.setChecked(v == valor)
        self._carregar_lista()

    def _selecao_mudou(self) -> None:
        item_id = self._tabela.id_selecionado()
        if item_id is not None:
            self._abrir_compromisso(item_id)

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "data_hora_inicio":
            return formatar_data_iso(dado.get("data_hora_inicio"))
        if chave == "hora":
            inicio = dado.get("data_hora_inicio") or ""
            return inicio[11:16] if len(inicio) >= 16 else ""
        if chave == "tipo":
            return dict(_TIPOS).get(dado.get("tipo"), "")
        if chave == "ordem_servico":
            num = dado.get("ordem_servico_numero")
            return f"Nº {num}" if num else "—"
        if chave == "status":
            return dict(_STATUS).get(dado.get("status"), "")
        return ""

    # -------------------------------------------------------------------- dados

    def _janela_mes(self) -> tuple[str, str]:
        inicio = QDate(self._mes.year(), self._mes.month(), 1)
        fim = inicio.addMonths(1).addDays(-1)
        return inicio.toString("yyyy-MM-dd") + "T00:00:00", fim.toString("yyyy-MM-dd") + "T23:59:59"

    def _carregar_periodo(self) -> None:
        inicio, fim = self._janela_mes()
        tarefas.rodar(
            lambda: self._api.listar_agendamentos(inicio=inicio, fim=fim),
            on_ok=lambda saida: self._receber_periodo(saida),
            on_erro=self._erro_carga,
        )

    def _receber_periodo(self, saida: dict) -> None:
        self._ultimos = saida.get("data", [])
        self._calendario.preencher(self._ultimos)
        self._atualizar_painel_dia()

    def _carregar_lista(self, offset: int = 0) -> None:
        inicio, fim = self._janela_mes()
        tarefas.rodar(
            lambda: self._api.listar_agendamentos(
                inicio=inicio,
                fim=fim,
                tipo=self._filtro_tipo or None,
                status=self._filtro_status or None,
                offset=offset,
            ),
            on_ok=lambda saida: self._tabela.preencher(saida.get("data", [])),
            on_erro=self._erro_carga,
        )

    def _carregar_os(self) -> None:
        tarefas.rodar(
            lambda: self._api.listar_os(tipo="os", limit=200),
            on_ok=lambda saida: self._preencher_os(saida.get("data", [])),
            on_erro=lambda _m: None,
        )

    def _preencher_os(self, os_lista: list[dict]) -> None:
        opcoes = [("", "Sem O.S.")]
        for osn in os_lista:
            numero = osn.get("numero")
            cliente = osn.get("cliente_nome") or "Consumidor final"
            opcoes.append((osn.get("id"), f"Nº {numero} — {cliente}"))
        self._campo_os = CampoCombo("O.S. vinculada", opcoes)
        self._montar_form()

    def _erro_carga(self, msg: str) -> None:
        QMessageBox.warning(self, "Agendamento", msg)

    # -------------------------------------------------------------------- ficha

    def _painel_form(self) -> QWidget:
        painel = QWidget()
        painel.setObjectName("card")
        self._painel_col = QVBoxLayout(painel)
        self._painel_col.setContentsMargins(0, 0, 0, 0)
        self._painel_col.setSpacing(0)
        self._painel_form = QScrollArea()
        self._painel_form.setWidgetResizable(True)
        self._painel_form.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._painel_col.addWidget(self._painel_form, 1)
        self._montar_form()
        painel.setMinimumWidth(330)
        return painel

    def _montar_form(self) -> None:
        if not hasattr(self, "_campo_os"):
            return  # lista de O.S. ainda não chegou; o painel é montado ao chegar
        conteudo = QWidget()
        conteudo.setMinimumWidth(330)
        grade = QVBoxLayout(conteudo)
        grade.setContentsMargins(16, 14, 16, 14)
        grade.setSpacing(10)

        self._form_titulo = ElideLabel(self.ROTULO_NOVO)
        self._form_titulo.setObjectName("titulo")
        grade.addWidget(self._form_titulo)

        if self._modo_leitura:
            aviso = QLabel("Modo leitura: consulta habilitada, escrita bloqueada.")
            aviso.setObjectName("bannerLeitura")
            grade.addWidget(aviso)

        self._titulo = CampoTexto("Título", maximo=160).obrigatorio()
        self._tipo = CampoCombo("Tipo", _TIPOS, "producao")
        self._inicio = CampoDataHora("Início", obrigatorio=True)
        self._fim = CampoDataHora("Término", obrigatorio=False)
        self._descricao = CampoArea("Descrição")
        self._status = CampoCombo("Status", _STATUS, "agendado")
        self._status.visivel(False)

        grade.addWidget(rotulo_secao("Compromisso"))
        g1 = grade_campos()
        dispor_campos(g1, [self._titulo, self._tipo])
        grade.addLayout(g1)
        g2 = grade_campos()
        dispor_campos(g2, [self._inicio, self._fim])
        grade.addLayout(g2)
        g3 = grade_campos()
        dispor_campos(g3, [self._campo_os, self._status])
        grade.addLayout(g3)
        # O status nasce oculto (só aparece ao editar); `visivel()` precisa
        # rodar DEPOIS de `dispor_campos`, senão só o combo é escondido e o
        # rótulo fica órfão na grade (achado da revisão de telas).
        self._status.visivel(False)
        g4 = grade_campos()
        dispor_campos(g4, [self._descricao.larga()])
        grade.addLayout(g4)
        grade.addStretch(1)

        rodape = QWidget()
        rodape.setObjectName("rodape")
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(16, 10, 16, 10)
        rl.addStretch(1)
        self._btn_concluir = QPushButton("Concluir")
        estado_sucesso(self._btn_concluir)
        self._btn_concluir.clicked.connect(self._concluir)
        self._btn_excluir = QPushButton("Excluir")
        estado_erro(self._btn_excluir)
        self._btn_excluir.clicked.connect(self._excluir)
        cancelar, self._btn_cancelar = botao_com_atalho("Cancelar", "Esc")
        salvar, self._btn_salvar = botao_com_atalho("Salvar", "F10", "primary")
        rl.addWidget(self._btn_concluir)
        rl.addWidget(self._btn_excluir)
        rl.addWidget(cancelar)
        rl.addWidget(salvar)

        self._btn_cancelar.clicked.connect(self._cancelar)
        self._btn_salvar.clicked.connect(self._salvar)
        self._painel_form.setWidget(conteudo)
        self._painel_col.addWidget(rodape)
        self._aplicar_modo_leitura()
    # ------------------------------------------------------------------ ações

    def _novo(self) -> None:
        if self._modo_leitura:
            return
        self._editando_id = None
        self._form_titulo.setText(self.ROTULO_NOVO)
        self._btn_salvar.setText("Salvar")
        self._titulo.definir("")
        self._tipo.definir("producao")
        self._inicio.definir(datetime.now().replace(second=0, microsecond=0))
        self._fim.definir(None)
        self._campo_os.definir("")
        self._status.definir("agendado")
        self._status.visivel(False)
        self._descricao.definir("")
        self._btn_concluir.hide()
        self._btn_excluir.hide()
        self._titulo.widget.setFocus()

    def _abrir_compromisso(self, item_id) -> None:
        if item_id is None:
            return
        tarefas.rodar(
            lambda: self._api.obter_agendamento(item_id),
            on_ok=self._receber_compromisso,
            on_erro=self._erro_carga,
        )

    def _receber_compromisso(self, dado: dict) -> None:
        self._editando_id = dado.get("id")
        self._form_titulo.setText(f"Agendamento Nº {self._editando_id}")
        self._btn_salvar.setText("Salvar Alterações")
        self._titulo.definir(dado.get("titulo") or "")
        self._tipo.definir(dado.get("tipo") or "producao")
        self._inicio.definir(dado.get("data_hora_inicio"))
        self._fim.definir(dado.get("data_hora_fim"))
        self._campo_os.definir(dado.get("ordem_servico_id"))
        self._status.definir(dado.get("status") or "agendado")
        self._status.visivel(True)
        self._descricao.definir(dado.get("descricao") or "")
        self._btn_concluir.setVisible(dado.get("status") != "concluido")
        self._btn_excluir.show()
        self._titulo.widget.setFocus()

    def _cancelar(self) -> None:
        # Esc reverte a ficha para um novo compromisso em branco.
        self._novo()

    def _payload(self) -> dict:
        fim = self._fim.valor()
        inicio = self._inicio.valor()
        if fim is not None and inicio is not None and fim < inicio:
            raise ValueError("O término deve ser igual ou posterior ao início.")
        os_id = self._campo_os.valor()
        return {
            "titulo": limpo(self._titulo.valor()),
            "tipo": self._tipo.valor(),
            "data_hora_inicio": inicio.isoformat() if inicio else None,
            "data_hora_fim": fim.isoformat() if fim else None,
            "descricao": limpo(self._descricao.valor()),
            "ordem_servico_id": os_id if os_id else None,
            "status": self._status.valor(),
        }

    def _validar(self):
        if not self._titulo.valido():
            return "Informe o título do compromisso.", self._titulo
        inicio = self._inicio.valor()
        fim = self._fim.valor()
        if inicio is None:
            return "Informe a data e hora de início.", self._inicio
        if fim is not None and fim < inicio:
            return "O término deve ser igual ou posterior ao início.", self._fim
        return None

    def _salvar(self) -> None:
        if self._modo_leitura:
            return
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Validação", msg)
            campo.widget.setFocus()
            return
        self._btn_salvar.setEnabled(False)
        payload = self._payload()
        if self._editando_id is None:
            tarefas.rodar(
                lambda: self._api.criar_agendamento(payload),
                on_ok=lambda d: self._salvo(d),
                on_erro=self._erro_salvar,
            )
        else:
            tarefas.rodar(
                lambda: self._api.atualizar_agendamento(self._editando_id, payload),
                on_ok=lambda d: self._salvo(d),
                on_erro=self._erro_salvar,
            )

    def _salvo(self, dado: dict) -> None:
        self._btn_salvar.setEnabled(not self._modo_leitura)
        self._carregar_periodo()
        self._carregar_lista()
        self._receber_compromisso(dado or {})

    def _erro_salvar(self, msg: str) -> None:
        self._btn_salvar.setEnabled(not self._modo_leitura)
        QMessageBox.critical(self, "Não foi possível salvar", msg)

    def _concluir(self) -> None:
        if self._editando_id is None or self._modo_leitura:
            return
        tarefas.rodar(
            lambda: self._api.concluir_agendamento(self._editando_id),
            on_ok=lambda d: self._salvo(d),
            on_erro=self._erro_salvar,
        )

    def _excluir(self) -> None:
        if self._editando_id is None or self._modo_leitura:
            return
        if (
            QMessageBox.question(
                self,
                "Excluir compromisso",
                "Excluir este agendamento?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        tarefas.rodar(
            lambda: self._api.remover_agendamento(self._editando_id),
            on_ok=lambda: self._excluido(),
            on_erro=self._erro_salvar,
        )

    def _excluido(self) -> None:
        self._novo()
        self._carregar_periodo()
        self._carregar_lista()

    def _aplicar_modo_leitura(self) -> None:
        for campo in (
            self._titulo, self._tipo, self._inicio, self._fim,
            self._campo_os, self._status, self._descricao,
        ):
            campo.habilitar(not self._modo_leitura)
        self._btn_novo.setEnabled(not self._modo_leitura)
        self._btn_salvar.setEnabled(not self._modo_leitura)
        self._btn_concluir.setEnabled(not self._modo_leitura)
        self._btn_excluir.setEnabled(not self._modo_leitura)
        # Em modo leitura (e antes de abrir um registro) as ações de edição ficam ocultas.
        self._btn_concluir.setVisible(False)
        self._btn_excluir.setVisible(False)
