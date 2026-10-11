"""Grade de listagem em alta densidade (padrão balcão dos mockups 2.x).

Linhas selecionáveis, sem edição in-place, com o objeto original guardado por
linha para o formulário lateral buscar os dados ao trocar de seleção.

As colunas dividem a largura disponível por pesos (`pesos`) — assim a lista não
gera rolagem horizontal em 1280px; textos que não couberem são elididos e
ficam acessíveis por tooltip. Sem registros, exibe um estado vazio central.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
)

LARGURA_MINIMA = 56


class TabelaDensa(QTableWidget):
    def __init__(
        self,
        colunas: list[str],
        rotulos: list[str] | None = None,
        pesos: list[int] | None = None,
    ) -> None:
        rotulos = rotulos or [c.upper() for c in colunas]
        super().__init__(0, len(colunas))
        self._colunas = colunas
        self._pesos = list(pesos) if pesos else [1] * len(colunas)
        self._pesos = (self._pesos + [1] * len(colunas))[: len(colunas)]
        self.formata = None
        self.setHorizontalHeaderLabels(rotulos)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalHeader().setVisible(False)
        cabecalho = self.horizontalHeader()
        cabecalho.setStretchLastSection(False)
        cabecalho.setHighlightSections(False)
        cabecalho.setSectionsMovable(False)
        cabecalho.setMinimumSectionSize(LARGURA_MINIMA)
        cabecalho.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.setMinimumHeight(320)

        self._vazio = QLabel("", self.viewport())
        self._vazio.setObjectName("vazioTabela")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setWordWrap(True)
        self._vazio.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._vazio.hide()

    # -------------------------------------------------------------- conteúdo

    def estado_vazio(self, texto: str) -> None:
        """Texto exibido centralizado quando a tabela não tem linhas."""
        self._vazio.setText(texto)
        self._atualizar_vazio()

    def preencher(self, linhas: list[dict]) -> None:
        """`linhas` são os objetos da API; as colunas pedem essas chaves via `chave_coluna`."""
        self.setRowCount(0)
        self.setRowCount(len(linhas))
        for r, dado in enumerate(linhas):
            for c, _nome in enumerate(self._colunas):
                texto = self.texto_para(dado, self._colunas[c])
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                item.setData(Qt.ItemDataRole.UserRole, dado)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole + 1, dado.get("id"))
                self.setItem(r, c, item)
        self._ajustar_larguras()
        self._atualizar_vazio()

    def texto_para(self, dado: dict, chave: str) -> str:
        """Hook para as páginas formatarem o texto de uma coluna (ex.: moeda)."""
        if self.formata is not None:
            return self.formata(dado, chave)
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

    # -------------------------------------------------------------- larguras

    def _ajustar_larguras(self) -> None:
        colunas = self.columnCount()
        if not colunas:
            return
        disponivel = self.viewport().width()
        if disponivel <= 0:
            return
        # Prioridade: maior peso primeiro; no empate, o índice menor fica. Quando
        # a lista estreita, as colunas de menor peso são ocultadas ("colunas
        # prioritárias") em vez de gerar rolagem lateral.
        ordem = sorted(range(colunas), key=lambda c: (-self._pesos[c], c))
        visiveis = list(ordem)
        while len(visiveis) > 1 and len(visiveis) * LARGURA_MINIMA > disponivel:
            visiveis.pop()
        mostrar = set(visiveis)
        for c in range(colunas):
            self.setColumnHidden(c, c not in mostrar)

        visiveis.sort()
        soma = sum(self._pesos[c] for c in visiveis) or 1
        larguras = {
            c: max(LARGURA_MINIMA, int(disponivel * self._pesos[c] / soma))
            for c in visiveis
        }
        # Garante que a soma não ultrapasse a viewport: sem rolagem lateral.
        excesso = sum(larguras.values()) - disponivel
        while excesso > 0:
            maior = max(visiveis, key=lambda c: larguras[c])
            if larguras[maior] <= LARGURA_MINIMA:
                break
            larguras[maior] -= 1
            excesso -= 1
        for c in visiveis:
            self.setColumnWidth(c, larguras[c])

    def resizeEvent(self, evento) -> None:  # noqa: N802 (API Qt)
        super().resizeEvent(evento)
        self._vazio.setGeometry(self.viewport().rect())
        self._ajustar_larguras()

    def _atualizar_vazio(self) -> None:
        self._vazio.setGeometry(self.viewport().rect())
        self._vazio.setVisible(self.rowCount() == 0 and bool(self._vazio.text()))

    # -------------------------------------------------------------- seleção

    def id_selecionado(self) -> int | None:
        item = self.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole + 1)

    def objeto_selecionado(self) -> dict | None:
        item = self.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def selecionar_id(self, item_id: int) -> None:
        for linha in range(self.rowCount()):
            item = self.item(linha, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole + 1) == item_id:
                self.selectRow(linha)
                return

    def limpar(self) -> None:
        self.setRowCount(0)
        self._atualizar_vazio()
