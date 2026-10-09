"""Grade de listagem em alta densidade (padrão balcão dos mockups 2.x).

Linhas selecionáveis, sem edição in-place, com o objeto original guardado por
linha para o formulário lateral buscar os dados ao trocar de seleção.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTableWidget,
    QTableWidgetItem,
)


class TabelaDensa(QTableWidget):
    def __init__(self, colunas: list[str], rotulos: list[str] | None = None) -> None:
        rotulos = rotulos or [c.upper() for c in colunas]
        super().__init__(0, len(colunas))
        self._colunas = colunas
        self.formata = None
        self.setHorizontalHeaderLabels(rotulos)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setHighlightSections(False)
        self.setMinimumHeight(320)

    def preencher(self, linhas: list[dict]) -> None:
        """`linhas` são os objetos da API; as colunas pedem essas chaves via `chave_coluna`."""
        self.setRowCount(0)
        self.setRowCount(len(linhas))
        for r, dado in enumerate(linhas):
            for c, _nome in enumerate(self._colunas):
                tentativa = self.texto_para(dado, self._colunas[c])
                item = QTableWidgetItem(tentativa)
                item.setData(Qt.ItemDataRole.UserRole, dado)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole + 1, dado.get("id"))
                self.setItem(r, c, item)
        self.resizeColumnsToContents()
        self.setColumnWidth(0, min(self.columnWidth(0), 90))

    def texto_para(self, dado: dict, chave: str) -> str:
        """Hook para as páginas formatarem o texto de uma coluna (ex.: moeda)."""
        if self.formata is not None:
            return self.formata(dado, chave)
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

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