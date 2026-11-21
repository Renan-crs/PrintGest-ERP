"""Diálogo estruturado para gerar variações de um produto pai.

Substitui o QInputDialog de texto livre: combos sugerem os domínios já usados
no catálogo e a lista mostra o SKU que será gerado antes de confirmar.
"""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


def _slug(valor: str | None) -> str:
    texto = re.sub(r"[^A-Za-z0-9]", "", (valor or "").strip())
    return texto.upper()[:8]


class DialogoVariacoes(QDialog):
    """Coleta combinações tamanho/marca/cor com preview do SKU.

    `valor()` devolve a lista de dicts no formato aceito por
    `POST /v1/produtos/variacoes/gerar`.
    """

    def __init__(
        self,
        produto_pai: dict,
        dominios: dict[str, list[str]] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gerar variações")
        self.setMinimumWidth(520)

        dominios = dominios or {}
        prefixo = _slug(produto_pai.get("codigo")) or "VAR"
        self._prefixo = prefixo
        self._combos: list[dict[str, str]] = []
        self._skus: set[str] = set()

        col = QVBoxLayout(self)
        col.addWidget(QLabel(
            "Monte as combinações. Cada linha gera uma variante filha com "
            "SKU único e estoque próprio. Combinações já existentes são "
            "ignoradas (idempotente)."
        ))
        col.addWidget(QLabel(f"Prefixo do SKU: {prefixo}"))

        form = QFormLayout()
        self._campos: dict[str, QComboBox] = {}
        opcoes_padrao = {
            "tamanho": ["P", "M", "G", "GG"],
            "marca": [],
            "cor": ["Azul", "Preto", "Branco"],
        }
        for chave, rotulo in (
            ("tamanho", "Tamanho"), ("marca", "Marca"), ("cor", "Cor")
        ):
            combo = QComboBox()
            combo.setEditable(True)
            valores = list(dict.fromkeys(
                dominios.get(chave) or opcoes_padrao[chave]
            ))
            combo.addItems(valores)
            combo.setCurrentText("")
            self._campos[chave] = combo
            form.addRow(rotulo, combo)
        col.addLayout(form)

        linha = QHBoxLayout()
        adicionar = QPushButton("Adicionar combinação")
        adicionar.clicked.connect(self._adicionar)
        remover = QPushButton("Remover selecionada")
        remover.clicked.connect(self._remover)
        linha.addWidget(adicionar)
        linha.addWidget(remover)
        col.addLayout(linha)

        self._lista = QListWidget()
        col.addWidget(self._lista)

        self._botoes = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._botoes.accepted.connect(self.accept)
        self._botoes.rejected.connect(self.reject)
        self._ok = self._botoes.button(QDialogButtonBox.StandardButton.Ok)
        self._ok.setEnabled(False)
        col.addWidget(self._botoes)

    def _sku(self, tamanho: str, marca: str, cor: str) -> str:
        partes = [self._prefixo, _slug(tamanho), _slug(marca), _slug(cor)]
        return "-".join(p for p in partes if p)[:64]

    def _adicionar(self) -> None:
        tamanho = self._campos["tamanho"].currentText().strip()
        marca = self._campos["marca"].currentText().strip()
        cor = self._campos["cor"].currentText().strip()
        if not any((tamanho, marca, cor)):
            QMessageBox.warning(
                self, "Variações", "Informe ao menos um atributo."
            )
            return
        sku = self._sku(tamanho, marca, cor)
        if sku in self._skus:
            QMessageBox.warning(
                self, "Variações", "Essa combinação já foi adicionada."
            )
            return
        self._skus.add(sku)
        self._combos.append({
            "tamanho": tamanho, "marca": marca, "cor": cor
        })
        item = QListWidgetItem(
            f"{tamanho or '—'} | {marca or '—'} | {cor or '—'}  →  {sku}"
        )
        item.setToolTip(sku)
        self._lista.addItem(item)
        self._ok.setEnabled(True)

    def _remover(self) -> None:
        atual = self._lista.currentRow()
        if atual < 0:
            return
        item = self._lista.takeItem(atual)
        self._skus.discard(item.toolTip())
        self._combos.pop(atual)
        self._ok.setEnabled(bool(self._combos))

    def valor(self) -> list[dict[str, str]]:
        return [dict(combo) for combo in self._combos]
