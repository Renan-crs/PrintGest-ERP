"""Busca global do cabeçalho — clientes, produtos e O.S. de um só campo.

Debounce (~250 ms) via `QTimer` para não disparar uma consulta a cada tecla;
o popup (`QListWidget`) lista sugestões carregadas em background (`rodar`).
Ao escolher um item, emite `navegar(módulo)` para a Tela Principal abrir a
página correspondente e `abrir_registro(id)` para telas futuras.

A consulta respeita o RBAC local: cada entidade só é pesquisada se o usuário
tiver acesso ao respectivo módulo (igual ao menu lateral).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from printgest.core.api import Api
from printgest.core.rbac import pode_abrir
from printgest.core.tarefas import rodar

MODULO_POR_ENTIDADE = {
    "clientes": "cliente",
    "produtos": "produto",
    "os": "os",
}


class BuscaGlobal(QWidget):
    """Campo de busca com sugestões para as três entidades mais usadas."""

    navegar = Signal(str)
    abrir_registro = Signal(str)

    def __init__(self, api: Api, nivel: str) -> None:
        super().__init__()
        self._api = api
        self._nivel = nivel
        self._pendentes = 0
        self._geracao = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._campo = QLineEdit()
        self._campo.setObjectName("buscaGlobal")
        self._campo.setPlaceholderText("Buscar clientes, produtos, O.S...")
        self._campo.setClearButtonEnabled(True)
        layout.addWidget(self._campo)

        self._sugestoes = QListWidget()
        self._sugestoes.setObjectName("sugestoesBusca")
        self._sugestoes.setMaximumHeight(220)
        self._sugestoes.hide()
        layout.addWidget(self._sugestoes)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._consultar)

        self._campo.textChanged.connect(self._agendar)
        self._sugestoes.itemClicked.connect(self._escolher)
        self.setFixedWidth(320)

    # ------------------------------------------------------------- entrada

    def _agendar(self, texto: str) -> None:
        if not texto.strip():
            self._geracao += 1  # invalida respostas ainda em voo
            self._sugestoes.clear()
            self._sugestoes.hide()
            return
        self._timer.start()

    def _consultar(self) -> None:
        texto = self._campo.text().strip()
        if not texto:
            return
        self._geracao += 1
        geracao = self._geracao
        self._sugestoes.clear()
        self._pendentes = 0
        for entidade, modulo in MODULO_POR_ENTIDADE.items():
            # Só pesquisa o que o usuário pode abrir (mesmo filtro do menu).
            if not pode_abrir(self._nivel, modulo):
                continue
            self._pendentes += 1
            if entidade == "os":
                chamada = lambda e=entidade, t=texto: self._api.listar_os(q=t, limit=6)
            else:
                chamada = (
                    lambda e=entidade, t=texto: self._api.listar(e, q=t, limit=6)
                )
            rodar(
                chamada,
                on_ok=lambda dados, e=entidade, m=modulo, g=geracao: self._receber(
                    e, m, dados, g
                ),
                on_erro=lambda _msg, g=geracao: self._concluir_pendencia(g),
            )

    def _receber(self, entidade: str, modulo: str, dados, geracao: int) -> None:
        if geracao != self._geracao:
            return  # resposta obsoleta de uma busca anterior
        registros = dados.get("data", []) if isinstance(dados, dict) else []
        for reg in registros[:6]:
            rotulo = self._rotulo(entidade, reg)
            item = QListWidgetItem(f"{rotulo} #{reg.get('id')} — {self._nome(entidade, reg)}")
            item.setData(Qt.ItemDataRole.UserRole, {"modulo": modulo, "id": reg.get("id")})
            self._sugestoes.addItem(item)
            item.setToolTip(f"Abrir {rotulo}")
        self._concluir_pendencia(geracao)

    def _concluir_pendencia(self, geracao: int) -> None:
        if geracao != self._geracao:
            return  # resposta obsoleta de uma busca anterior
        self._pendentes = max(0, self._pendentes - 1)
        if self._pendentes == 0:
            self._sugestoes.setVisible(self._sugestoes.count() > 0)

    def _escolher(self, item: QListWidgetItem) -> None:
        dados = item.data(Qt.ItemDataRole.UserRole) or {}
        modulo = dados.get("modulo")
        id_registro = dados.get("id")
        if modulo:
            self.navegar.emit(modulo)
        if id_registro is not None:
            self.abrir_registro.emit(str(id_registro))

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _nome(entidade: str, reg: dict) -> str:
        if entidade == "os":
            return reg.get("cliente_nome") or reg.get("descricao") or "—"
        return reg.get("nome_razao") or reg.get("nome") or "—"

    @staticmethod
    def _rotulo(entidade: str, reg: dict) -> str:
        base = {"clientes": "Cliente", "produtos": "Produto", "os": "O.S."}[entidade]
        if entidade == "os":
            return f"{base} {reg.get('numero') or reg.get('id')}"
        return f"{base} {reg.get('id')}"