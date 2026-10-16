"""Quadro Kanban (visão de Projetos): colunas por status, cartões elididos.

Componente reutilizável e "burro": ele não acessa a rede. O dono da tela
declara as colunas `[(chave, rótulo), ...]`, fornece uma fábrica de cartões
`fabrica(dado) -> CartaoKanban` e chama `preencher({chave: [dados]})` quando os
dados chegam. Assim o mesmo quadro serve a Projetos hoje e a qualquer outro
fluxo por etapas amanhã.

**Movimentação.** Os cartões podem ser arrastados entre colunas (gesto do
mouse) e, para acesso por teclado, o menu de contexto do cartão (tecla
Aplicativo / Shift+F10) oferece "Mover para → <etapa>". O quadro apenas
*anuncia* o movimento pelo sinal `movido(id, chave_destino)`; quem decide se ele
é válido (regra de transição de status) e persiste é o dono da tela — por isso o
componente continua sem tocar a rede.

Sem rolagem por coluna: o quadro inteiro tem **uma** barra vertical (as colunas
crescem juntas) e a barra horizontal só aparece se as colunas não couberem.
Cada cartão é focável — dá para percorrer com Tab e abrir com Enter/Espaço.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from printgest.ui import animacao
from printgest.ui.widgets import ElideLabel, badge

# Formato usado para carregar o id do cartão durante o arraste.
MIME_CARTAO = "application/x-printgest-cartao"


class CartaoKanban(QFrame):
    """Cartão clicável de um registro. Emite `selecionado(id)` no clique/Enter.

    Também pode ser **arrastado** (o quadro injeta `coluna_origem`/`destinos`) e
    oferece o menu de contexto "Mover para" como alternativa por teclado.
    """

    selecionado = Signal(int)
    mover_solicitado = Signal(int, str)

    def __init__(
        self,
        dado_id,
        titulo: str,
        subtitulo: str,
        rodape: str,
        atrasado: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("cartaoKanban")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._id = dado_id

        # Injetados por `QuadroKanban` (arraste + menu de contexto).
        self.coluna_origem: str | None = None
        self.destinos: list[tuple[str, str]] = []
        self.arrastavel = True
        self._inicio: QPoint | None = None
        self._arrastando = False

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(10, 8, 10, 8)
        coluna.setSpacing(2)

        topo = QWidget()
        linha = QHBoxLayout(topo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        self._titulo = ElideLabel(titulo)
        self._titulo.setObjectName("tituloCartao")
        linha.addWidget(self._titulo, 1)
        if atrasado:
            linha.addWidget(badge("Atrasado", "erro"), 0)
        coluna.addWidget(topo)

        self._subtitulo = ElideLabel(subtitulo)
        coluna.addWidget(self._subtitulo)

        self._rodape = ElideLabel(rodape)
        self._rodape.setProperty("role", "muted")
        coluna.addWidget(self._rodape)

        self.setToolTip(" · ".join(p for p in (titulo, subtitulo, rodape) if p))

    @property
    def id_registro(self):
        return self._id

    # ------------------------------------------------------------- interação

    def mousePressEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if evento.button() == Qt.MouseButton.LeftButton:
            self._inicio = evento.position().toPoint()
            self._arrastando = False
        super().mousePressEvent(evento)

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if self._inicio is None or not self.arrastavel:
            return super().mouseMoveEvent(evento)
        if not (evento.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(evento)
        distancia = (evento.position().toPoint() - self._inicio).manhattanLength()
        if distancia < QApplication.startDragDistance():
            return super().mouseMoveEvent(evento)
        self._arrastando = True
        self._preparar_arraste().exec(Qt.DropAction.MoveAction)

    def _preparar_arraste(self) -> QDrag:
        """Monta o `QDrag` com o id do cartão (sem executá-lo — testável).

        Quando o movimento está habilitado, o cartão vira um **pixmap elevado**
        (sombra) sob o cursor e o *hot spot* respeita **onde o usuário pegou**
        (§2 direct manipulation) — o cartão não "pula" para o centro da mão.

        O menu de contexto "Mover para" (Shift+F10) continua sendo o caminho por
        teclado; por isso o arraste é apenas o gesto do mouse.
        """
        arraste = QDrag(self)
        dados = QMimeData()
        dados.setData(MIME_CARTAO, str(self._id).encode("utf-8"))
        arraste.setMimeData(dados)
        pixmap = animacao.pixmap_com_sombra(self)
        if pixmap is not None and not pixmap.isNull():
            arraste.setPixmap(pixmap)
            if self._inicio is not None:
                # Preserva o offset do "agarre" (clampado ao cartão).
                x = min(max(self._inicio.x(), 0), pixmap.width())
                y = min(max(self._inicio.y(), 0), pixmap.height())
                arraste.setHotSpot(QPoint(x, y))
        return arraste

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        arrastou = self._arrastando
        self._inicio = None
        self._arrastando = False
        if (
            not arrastou
            and evento.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(evento.position().toPoint())
        ):
            self.selecionado.emit(self._id)
        super().mouseReleaseEvent(evento)

    def contextMenuEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        destinos = [
            (chave, rotulo)
            for chave, rotulo in self.destinos
            if chave != self.coluna_origem
        ]
        if not self.arrastavel or not destinos:
            return super().contextMenuEvent(evento)
        menu = QMenu(self)
        for chave, rotulo in destinos:
            acao = menu.addAction(f"Mover para {rotulo}")
            acao.triggered.connect(
                lambda _marcado=False, destino=chave: self.mover_solicitado.emit(
                    self._id, destino
                )
            )
        menu.exec(evento.globalPos())
        evento.accept()

    def keyPressEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if evento.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.selecionado.emit(self._id)
            return
        super().keyPressEvent(evento)


class ColunaKanban(QFrame):
    """Uma etapa do quadro: cabeçalho (rótulo + contagem), pilha de cartões e
    alvo de soltura (arrastar-e-soltar entre colunas)."""

    selecionado = Signal(int)
    recebido = Signal(int, str)

    def __init__(self, chave: str, rotulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chave = chave
        self.setObjectName("colunaKanban")
        self.setMinimumWidth(168)
        self._aceitar_drop = True
        self.setAcceptDrops(True)

        coluna = QVBoxLayout(self)
        coluna.setContentsMargins(8, 8, 8, 8)
        coluna.setSpacing(8)

        cabecalho = QWidget()
        linha = QHBoxLayout(cabecalho)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        self._titulo = ElideLabel(rotulo.upper())
        self._titulo.setObjectName("tituloColunaKanban")
        self._contagem = ElideLabel("0")
        self._contagem.setObjectName("contagemKanban")
        self._contagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        linha.addWidget(self._titulo, 1)
        linha.addWidget(self._contagem, 0)
        coluna.addWidget(cabecalho)

        corpo = QWidget()
        self._corpo = QVBoxLayout(corpo)
        self._corpo.setContentsMargins(0, 0, 0, 0)
        self._corpo.setSpacing(8)
        self._vazio = ElideLabel("Sem registros")
        self._vazio.setProperty("role", "muted")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._corpo.addWidget(self._vazio)

        self._cartoes = QVBoxLayout()
        self._cartoes.setContentsMargins(0, 0, 0, 0)
        self._cartoes.setSpacing(8)
        self._corpo.addLayout(self._cartoes)
        self._corpo.addStretch(1)
        coluna.addWidget(corpo, 1)

    def preencher(
        self, itens: list[dict], fabrica: Callable[[dict], CartaoKanban]
    ) -> None:
        self._contagem.setText(str(len(itens)))
        self._vazio.setVisible(not itens)
        while self._cartoes.count():
            item = self._cartoes.takeAt(0)
            antigo = item.widget()
            if antigo is not None:
                antigo.setParent(None)
                antigo.deleteLater()
        for dado in itens:
            cartao = fabrica(dado)
            cartao.selecionado.connect(self.selecionado)
            self._cartoes.addWidget(cartao)
        self._cartoes.addStretch(1)

    def cartoes(self) -> list[CartaoKanban]:
        achados = []
        for indice in range(self._cartoes.count()):
            widget = self._cartoes.itemAt(indice).widget()
            if isinstance(widget, CartaoKanban):
                achados.append(widget)
        return achados

    # ------------------------------------------------------- arrastar/soltar

    def aceitar_drop(self, ligado: bool) -> None:
        self._aceitar_drop = ligado
        self.setAcceptDrops(ligado)
        if not ligado:
            self._destacar(False)

    def dragEnterEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if self._aceitar_drop and evento.mimeData().hasFormat(MIME_CARTAO):
            self._destacar(True)
            evento.acceptProposedAction()

    def dragMoveEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if self._aceitar_drop and evento.mimeData().hasFormat(MIME_CARTAO):
            evento.acceptProposedAction()

    def dragLeaveEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        self._destacar(False)
        super().dragLeaveEvent(evento)

    def dropEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        self._destacar(False)
        if not self._aceitar_drop or not evento.mimeData().hasFormat(MIME_CARTAO):
            return
        try:
            item_id = int(bytes(evento.mimeData().data(MIME_CARTAO)).decode("utf-8"))
        except (TypeError, ValueError):
            return
        evento.acceptProposedAction()
        self.recebido.emit(item_id, self.chave)

    def _destacar(self, ligado: bool) -> None:
        if bool(self.property("alvoDrop")) == ligado:
            return
        self.setProperty("alvoDrop", ligado)
        estilo = self.style()
        estilo.unpolish(self)
        estilo.polish(self)
        self.update()


class QuadroKanban(QWidget):
    """Painel horizontal de colunas (`ColunaKanban`), uma por etapa."""

    selecionado = Signal(int)
    movido = Signal(int, str)

    def __init__(
        self,
        colunas: list[tuple[str, str]],
        fabrica: Callable[[dict], CartaoKanban],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fabrica = fabrica
        self._rotulos = list(colunas)
        self._colunas: dict[str, ColunaKanban] = {}
        self._permite_movimento = True

        self._area = QScrollArea()
        self._area.setObjectName("areaQuadro")
        self._area.setWidgetResizable(True)
        self._area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        interno = QWidget()
        interno.setObjectName("interiorQuadro")
        linha = QHBoxLayout(interno)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        for chave, rotulo in colunas:
            coluna = ColunaKanban(chave, rotulo)
            coluna.selecionado.connect(self.selecionado)
            coluna.recebido.connect(self.movido)
            linha.addWidget(coluna, 1)
            self._colunas[chave] = coluna
        self._area.setWidget(interno)

        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.addWidget(self._area)

    def preencher(self, por_coluna: dict[str, list[dict]]) -> None:
        for chave, coluna in self._colunas.items():
            coluna.preencher(por_coluna.get(chave, []), self._fabrica)
            coluna.aceitar_drop(self._permite_movimento)
            for cartao in coluna.cartoes():
                self._preparar_cartao(cartao, chave)

    def permitir_movimento(self, ligado: bool) -> None:
        """Liga/desliga o arraste (ex.: modo leitura da licença)."""
        self._permite_movimento = ligado
        for chave, coluna in self._colunas.items():
            coluna.aceitar_drop(ligado)
            for cartao in coluna.cartoes():
                self._preparar_cartao(cartao, chave)

    def _preparar_cartao(self, cartao: CartaoKanban, chave: str) -> None:
        cartao.coluna_origem = chave
        cartao.arrastavel = self._permite_movimento
        cartao.destinos = list(self._rotulos) if self._permite_movimento else []
        cartao.mover_solicitado.connect(self.movido)

    def coluna(self, chave: str) -> ColunaKanban:
        return self._colunas[chave]

    def contagem(self, chave: str) -> int:
        return len(self._colunas[chave].cartoes())

    def coluna_do(self, item_id) -> str | None:
        """Chave da coluna onde o cartão `item_id` está, ou None."""
        for chave, coluna in self._colunas.items():
            if any(c.id_registro == item_id for c in coluna.cartoes()):
                return chave
        return None
