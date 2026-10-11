"""Quadro Kanban (visão de Projetos): colunas por status, cartões elididos.

Componente reutilizável e "burro": ele não acessa a rede. O dono da tela
declara as colunas `[(chave, rótulo), ...]`, fornece uma fábrica de cartões
`fabrica(dado) -> CartaoKanban` e chama `preencher({chave: [dados]})` quando os
dados chegam. Assim o mesmo quadro serve a Projetos hoje e a qualquer outro
fluxo por etapas amanhã.

Sem rolagem por coluna: o quadro inteiro tem **uma** barra vertical (as colunas
crescem juntas) e a barra horizontal só aparece se as colunas não couberem.
Cada cartão é focável — dá para percorrer com Tab e abrir com Enter/Espaço.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from printgest.ui.widgets import ElideLabel, badge


class CartaoKanban(QFrame):
    """Cartão clicável de um registro. Emite `selecionado(id)` no clique/Enter."""

    selecionado = Signal(int)

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

    def mouseReleaseEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        if evento.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            evento.position().toPoint()
        ):
            self.selecionado.emit(self._id)
        super().mouseReleaseEvent(evento)

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
    """Uma etapa do quadro: cabeçalho (rótulo + contagem) e pilha de cartões."""

    selecionado = Signal(int)

    def __init__(self, chave: str, rotulo: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chave = chave
        self.setObjectName("colunaKanban")
        self.setMinimumWidth(168)

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


class QuadroKanban(QWidget):
    """Painel horizontal de colunas (`ColunaKanban`), uma por etapa."""

    selecionado = Signal(int)

    def __init__(
        self,
        colunas: list[tuple[str, str]],
        fabrica: Callable[[dict], CartaoKanban],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._fabrica = fabrica
        self._colunas: dict[str, ColunaKanban] = {}

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
            linha.addWidget(coluna, 1)
            self._colunas[chave] = coluna
        self._area.setWidget(interno)

        fora = QVBoxLayout(self)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.addWidget(self._area)

    def preencher(self, por_coluna: dict[str, list[dict]]) -> None:
        for chave, coluna in self._colunas.items():
            coluna.preencher(por_coluna.get(chave, []), self._fabrica)

    def coluna(self, chave: str) -> ColunaKanban:
        return self._colunas[chave]

    def contagem(self, chave: str) -> int:
        return len(self._colunas[chave].cartoes())
