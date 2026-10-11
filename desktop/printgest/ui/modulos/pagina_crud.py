"""Base comum dos cadastros (clientes, fornecedores, produtos, categorias...).

Split padrão dos mockups 2.x: lista densa à esquerda (busca F2, filtros,
paginação) e formulário em drawer à direita. Persistência pelo CRUD genérico do
daemon (`/v1/{entidade}`). Em modo leitura, as ações de escrita são
desabilitadas (a API também responde 423).

A subclasse declara `ENTIDADE`/`CHAVES`/`COLUNAS`/`FILTROS` e os hooks:
`_secoes()` (lista de (título, [campos])), `_preencher_campos(dado)`,
`_padroes_do_form()`, `_payload()` e `_formatar_texto(dado, chave)`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.busca import CampoBusca
from printgest.ui.formulario import (
    CampoCheck,
    dispor_campos,
    grade_campos,
    rotulo_secao,
)
from printgest.ui.paginador import LOTE, Paginador
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import ElideLabel, FlowLayout, botao_com_atalho


class PaginaCrud(QWidget):
    solicitado_detalhe = Signal(int)

    ENTIDADE = ""
    ROTULO_PAGINA = "Cadastro"
    ROTULO_NOVO = "Novo Registro"
    GRUPO_LISTA = "REGISTROS"
    CHAVES: list[str] = []
    COLUNAS: list[str] = []
    PESOS: list[int] = []
    FILTROS: list[tuple[str, str]] = []
    CHAVE_FILTRO = ""
    FILTRO_LOCAL = False
    LUGAR_BUSCA = "Buscar..."
    CAMPO_NOME = "nome_razao"
    ROTULO_EXPORTAR = "Exportar Excel"
    VAZIO = "Nenhum registro encontrado. Clique em {novo} (F6)."

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._linhas: list[dict] = []
        self._total = 0
        self._offset = 0
        self._seq = 0
        self._filtro = ""
        self._editando_id: int | None = None
        self._lista_secoes = self._secoes()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self._barra_titulo())
        layout.addWidget(self._barra_busca())
        layout.addWidget(self._split(), 1)

        self._montar_form()
        self._conectar_campos()
        self._instalar_atalhos()
        self.recarregar()

    # ----------------------------------------------------------- construção

    def _instalar_atalhos(self) -> None:
        """Atalhos do cadastro: F6 = Novo (nesta tela), F10 = Salvar, Esc = cancelar."""
        QShortcut(QKeySequence("F6"), self, self._novo)
        QShortcut(QKeySequence("F10"), self, self._salvar)
        QShortcut(QKeySequence("Esc"), self, self._limpar_form)

    def _campos(self) -> list:
        todos: list = []
        for _titulo, campos in self._lista_secoes:
            todos.extend(campos)
        return todos

    def _secoes(self):
        """Subclasse: retorna lista de (título da seção, [campos]); título '' oculta o rótulo."""
        raise NotImplementedError

    def _barra_titulo(self) -> QWidget:
        caixa = QWidget()
        layout = QHBoxLayout(caixa)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        titulo = ElideLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        layout.addWidget(titulo, 1)

        for badge_extra in self._badges_barra():
            layout.addWidget(badge_extra)

        novo, self._btn_novo = botao_com_atalho(self.ROTULO_NOVO, "F6", "primary")
        exp, self._btn_exportar = botao_com_atalho(self.ROTULO_EXPORTAR, "")
        layout.addWidget(novo)
        layout.addWidget(exp)
        self._btn_novo.clicked.connect(self._novo)
        self._btn_exportar.clicked.connect(self._exportar)
        return caixa

    def _barra_busca(self) -> QWidget:
        caixa = QWidget()
        layout = QHBoxLayout(caixa)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._busca = CampoBusca(self.LUGAR_BUSCA)
        self._busca.buscado.connect(lambda q: self.recarregar(q))
        layout.addWidget(self._busca, 1)

        self._btn_filtros: dict[str, QPushButton] = {}
        if self.FILTROS:
            filtros = QWidget()
            fluxo = FlowLayout(filtros, espaco_h=8, espaco_v=8)
            for valor, rotulo in self.FILTROS:
                botao = QPushButton(rotulo)
                botao.setCheckable(True)
                botao.setObjectName("chaveRapida")
                if valor == "":
                    botao.setChecked(True)
                botao.clicked.connect(lambda _=False, v=valor: self._aplicar_filtro(v))
                self._btn_filtros[valor] = botao
                fluxo.addWidget(botao)
            layout.addWidget(filtros, 0)
        return caixa

    def _split(self) -> QSplitter:
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(10)

        esquerda = QWidget()
        esquerda.setObjectName("card")
        col = QVBoxLayout(esquerda)
        # Folga no topo do card: separa o cabeçalho da tabela da borda.
        col.setContentsMargins(0, 8, 0, 0)
        col.setSpacing(0)

        self._tabela = TabelaDensa(self.CHAVES, self.COLUNAS, self.PESOS or None)
        self._tabela.formata = self._formatar_texto
        self._tabela.estado_vazio(self.VAZIO.format(novo=self.ROTULO_NOVO))
        self._tabela.itemSelectionChanged.connect(self._selecao_mudou)
        col.addWidget(self._tabela, 1)

        self._paginador = Paginador()
        self._paginador.mudou.connect(lambda offset: self.recarregar(self._busca.texto(), offset))
        pag_linha = QWidget()
        pag_layout = QHBoxLayout(pag_linha)
        pag_layout.setContentsMargins(14, 8, 14, 8)
        pag_layout.addWidget(self._paginador)
        col.addWidget(pag_linha)

        divisor.addWidget(esquerda)

        painel = QWidget()
        painel.setObjectName("card")
        self._painel_col = QVBoxLayout(painel)
        self._painel_col.setContentsMargins(0, 0, 0, 0)
        self._painel_col.setSpacing(0)

        self._painel_form = QScrollArea()
        self._painel_form.setWidgetResizable(True)
        self._painel_form.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._painel_col.addWidget(self._painel_form, 1)

        # Largura útil para a grade de 2 colunas; a lista fica com o restante.
        painel.setMinimumWidth(520)
        divisor.addWidget(painel)

        divisor.setStretchFactor(0, 1)
        divisor.setStretchFactor(1, 0)
        divisor.setSizes([700, 520])
        return divisor

    def _montar_form(self) -> None:
        conteudo = QWidget()
        conteudo.setMinimumWidth(460)
        self._form_grade = QVBoxLayout(conteudo)
        self._form_grade.setContentsMargins(16, 14, 16, 14)
        self._form_grade.setSpacing(10)

        self._form_titulo = ElideLabel(self.ROTULO_NOVO)
        self._form_titulo.setObjectName("titulo")
        self._form_grade.addWidget(self._form_titulo)

        if self._modo_leitura:
            aviso = QLabel("Modo leitura: consulta habilitada, escrita bloqueada.")
            aviso.setObjectName("bannerLeitura")
            self._form_grade.addWidget(aviso)

        for titulo_secao, campos in self._lista_secoes:
            if titulo_secao:
                self._form_grade.addWidget(rotulo_secao(titulo_secao))
            grade = grade_campos()
            dispor_campos(grade, campos)
            self._form_grade.addLayout(grade)

        self._form_grade.addStretch(1)

        # Rodapé fixo: fora da área rolável, sempre visível.
        rodape = QWidget()
        rodape.setObjectName("rodape")
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(16, 10, 16, 10)
        rl.addStretch(1)
        self._acoes_extra = self._acao_extra()
        for botao in self._acoes_extra:
            rl.addWidget(botao)
        cancelar, self._btn_cancelar = botao_com_atalho("Cancelar", "Esc")
        salvar, self._btn_salvar = botao_com_atalho("Salvar Alterações", "F10", "primary")
        rl.addWidget(cancelar)
        rl.addWidget(salvar)

        self._btn_cancelar.clicked.connect(self._limpar_form)
        self._btn_salvar.clicked.connect(self._salvar)

        self._painel_form.setWidget(conteudo)
        self._painel_col.addWidget(rodape)
        self._aplicar_modo_leitura_acoes()

    def _conectar_campos(self) -> None:
        """Hook: subclasse liga sinais que dependem de campos do formulário."""

    def _acao_extra(self) -> list:
        """Hook: subclasse acrescenta ações ao rodapé do formulário (ex.: Avançar Status)."""
        return []

    def _badges_barra(self) -> list:
        """Hook: subclasse anexa badges de KPI à barra de título (ex.: itens, valor)."""
        return []

    def _aplicar_modo_leitura_acoes(self) -> None:
        for botao in (self._btn_novo, self._btn_salvar, self._btn_cancelar):
            botao.setEnabled(not self._modo_leitura)
        for extra in getattr(self, "_acoes_extra", []):
            extra.setEnabled(not self._modo_leitura)
            for botao in extra.findChildren(QPushButton):
                botao.setEnabled(not self._modo_leitura)
        for campo in self._campos():
            campo.habilitar(not self._modo_leitura)

    # ------------------------------------------------------------- filtros

    def _aplicar_filtro(self, valor: str) -> None:
        self._filtro = valor
        for v, botao in self._btn_filtros.items():
            botao.setChecked(v == valor)
        self.recarregar(self._busca.texto())

    def _aplicar_filtro_local(self, linhas: list[dict]) -> list[dict]:
        if not self._filtro or not self.CHAVE_FILTRO:
            return linhas
        return [r for r in linhas if r.get(self.CHAVE_FILTRO) == self._filtro]

    # ------------------------------------------------------------ carregar

    def recarregar(self, q: str = "", offset: int | None = None) -> None:
        if offset is None:
            offset = self._offset
        self._seq += 1
        seq = self._seq

        def _receber(saida: dict) -> None:
            # Respostas de busca/paginação podem chegar fora de ordem; só vale a
            # última chamada disparada (a mais antiga é descartada).
            if seq != self._seq:
                return
            self._recebidos(q, offset, saida)

        # Filtro de campo (ex.: `tipo_pessoa`) vai ao servidor, para paginar sobre
        # o conjunto filtrado — não apenas recortar a página atual.
        filtros = {}
        if self.CHAVE_FILTRO and self._filtro and not self.FILTRO_LOCAL:
            filtros[self.CHAVE_FILTRO] = self._filtro
        rodar(
            lambda: self._listar(q, offset, filtros),
            on_ok=_receber,
            on_erro=lambda msg: self._erro_carga(msg),
        )

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        """Hook: subclasse troca o endpoint de listagem mantendo a guarda `_seq`.

        Recebe os `filtros` já resolvidos a partir de `CHAVE_FILTRO`/`_filtro`.
        """
        return self._api.listar_com_filtros(
            self.ENTIDADE, q=q, limit=LOTE, offset=offset, **filtros
        )

    def _recebidos(self, q: str, offset: int, saida: dict) -> None:
        self._linhas = saida["data"]
        self._total = saida["total"]
        self._offset = offset
        self._paginador.atualizar(self._total, offset, LOTE)
        self._tabela.preencher(self._aplicar_filtro_local(self._linhas))

    def _erro_carga(self, msg: str) -> None:
        self._tabela.limpar()
        self._form_titulo.setText(f"Erro ao carregar {self.ENTIDADE}")
        QMessageBox.warning(self, "Local API Service", msg)

    # ------------------------------------------------------------ seleção

    def _selecao_mudou(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            return
        self._carregar_no_form(dado)

    def _carregar_no_form(self, dado: dict) -> None:
        self._editando_id = dado.get("id")
        rotulo = self._rotulo_registro(dado)
        titulo = f"Editando {self._numero_registro(dado.get('id'))}"
        if rotulo:
            titulo = f"{titulo}: {rotulo}"
        self._form_titulo.setText(titulo)
        self._preencher_campos(dado)

    def _rotulo_registro(self, dado: dict) -> str:
        for chave in (self.CAMPO_NOME, "nome", "descricao", "id"):
            if dado.get(chave):
                return str(dado[chave])
        return ""

    def _numero_registro(self, item_id) -> str:
        return f"#{item_id:05d}" if isinstance(item_id, int) else "NOVO"

    def _preencher_campos(self, dado: dict) -> None:
        """Subclasse: preenche os campos a partir de `dado` (registro da API)."""
        raise NotImplementedError

    def _novo(self) -> None:
        self._limpar_form()
        primeiro = self._campos()[0]
        if getattr(primeiro, "widget", None) is not None:
            primeiro.widget.setFocus()

    def _limpar_form(self) -> None:
        self._editando_id = None
        self._form_titulo.setText(self.ROTULO_NOVO)
        for campo in self._campos():
            if isinstance(campo, CampoCheck):
                campo.definir(False)
            else:
                campo.definir(None)
        self._padroes_do_form()

    def _padroes_do_form(self) -> None:
        """Subclasse: valores padrão aplicados depois de limpar os campos."""

    # ---------------------------------------------------------------- salvar

    def _payload(self) -> dict:
        raise NotImplementedError

    def _validar(self):
        """Retorna (mensagem, campo) quando inválido; None se OK."""
        return None

    def _salvar(self) -> None:
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Validação", msg)
            campo.widget.setFocus()
            return
        self._btn_salvar.setEnabled(False)  # trava contra duplo POST (F10 + Enter)
        payload = self._payload()
        if self._editando_id is None:
            rodar(
                lambda: self._api.criar(self.ENTIDADE, payload),
                on_ok=self._salvo,
                on_erro=lambda msg: self._erro_salvar(msg),
            )
        else:
            item_id = self._editando_id
            rodar(
                lambda: self._api.atualizar(self.ENTIDADE, item_id, payload),
                on_ok=self._salvo,
                on_erro=lambda msg: self._erro_salvar(msg),
            )

    def _salvo(self, dado: dict) -> None:
        self._btn_salvar.setEnabled(True)
        # Cadastro mudou: combos que listam esta entidade precisam recarregar.
        catalogos.invalidar(self.ENTIDADE)
        self.recarregar(self._busca.texto())
        self._tabela.selecionar_id(dado["id"])
        self.solicitado_detalhe.emit(dado["id"])

    def _erro_salvar(self, msg: str) -> None:
        self._btn_salvar.setEnabled(True)
        QMessageBox.critical(self, "Não foi possível salvar", msg)

    # --------------------------------------------------------------- extras

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "id":
            ident = dado.get("id")
            return f"#{ident:05d}" if isinstance(ident, int) else ""
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

    def _exportar(self) -> None:
        QMessageBox.information(
            self,
            self.ROTULO_EXPORTAR,
            "Exportação para planilha estará disponível na próxima etapa.",
        )