"""Módulo Relatórios (PRD v2.1 §1.7 / telas_e_fluxos §1.7) — relatórios operacionais.

Quatro relatórios sob o menu "Relatórios", reunidos num host com sub-abas:

- **Vendas por Período** — faturamento, ticket médio, evolução.
- **Clientes que Mais Compram** — ranking por volume/valor, recência.
- **Serviços Mais Executados** — frequência, receita por serviço.
- **Aniversariantes do Mês** — lista com contato, faixa etária, envio de parabéns.

Todos abrem em modo leitura (consulta) — sem escrita. RBAC: GERENTE+ (mesma
regra do RBAC do menu — `core/rbac.py`).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from printgest.core.rbac import pode_abrir
from printgest.ui.widgets import ElideLabel, botao_com_atalho


# =============================================================== host


class PaginaRelatorios(QWidget):
    """Menu "Relatórios": hospeda as sub-abas conforme o perfil do usuário."""

    def __init__(self, api, modo_leitura: bool = False, nivel: str | None = None) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        candidatas = [
            ("rel_vendas", "Vendas por Período", PaginaRelVendas),
            ("rel_clientes", "Clientes que Mais Compram", PaginaRelClientes),
            ("rel_servicos", "Serviços Mais Executados", PaginaRelServicos),
            ("rel_aniversariantes", "Aniversariantes", PaginaRelAniversariantes),
        ]
        # RBAC não hierárquico: item interno exige GERENTE+.
        self._abas = [
            (rotulo, classe)
            for item_id, rotulo, classe in candidatas
            if nivel is None or pode_abrir(nivel, item_id)
        ]
        self._atual: QWidget | None = None

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._barra())
        self._corpo = QWidget()
        self._corpo_layout = QVBoxLayout(self._corpo)
        self._corpo_layout.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self._corpo, 1)

        if self._abas:
            self._trocar(0)
        else:
            restrito = QLabel("Acesso restrito a gerentes e administradores.")
            restrito.setObjectName("subtitulo")
            self._corpo_layout.addWidget(restrito)

    def _barra(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 16, 20, 0)
        linha.setSpacing(8)
        titulo = ElideLabel("Relatórios")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo)
        linha.addStretch(1)
        self._botoes = []
        for indice, (rotulo, _classe) in enumerate(self._abas):
            botao = QPushButton(rotulo)
            botao.setObjectName("chaveRapida")
            botao.setCheckable(True)
            botao.setChecked(indice == 0)
            botao.clicked.connect(lambda _=False, i=indice: self._trocar(i))
            self._botoes.append(botao)
            linha.addWidget(botao)
        return caixa

    def _trocar(self, indice: int) -> None:
        _rotulo, classe = self._abas[indice]
        pagina = classe(self._api, modo_leitura=True)
        if self._atual is not None:
            self._corpo_layout.removeWidget(self._atual)
            self._atual.deleteLater()
        self._corpo_layout.addWidget(pagina)
        self._atual = pagina
        for i, botao in enumerate(self._botoes):
            botao.setChecked(i == indice)


# =============================================================== placeholder pages


class _PaginaRelatorioBase(QWidget):
    """Base comum para páginas de relatório (somente leitura, estado vazio)."""

    ROTULO_PAGINA = "Relatório"

    def __init__(self, api, modo_leitura: bool = True) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        titulo = ElideLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        layout.addWidget(titulo)

        if self._modo_leitura:
            aviso = QLabel("Relatório em construção — estrutura de dados a definir.")
            aviso.setObjectName("bannerLeitura")
            layout.addWidget(aviso)

        vazio = QLabel("Esta tela será implementada na próxima fase.\n"
                       "Dados necessários: consulta SQL / API dedicada.")
        vazio.setObjectName("vazioTabela")
        vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vazio.setWordWrap(True)
        layout.addWidget(vazio, 1)

        # Rodapé com atalhos padrão
        rodape = QWidget()
        rodape.setObjectName("rodape")
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(16, 10, 16, 10)
        rl.addStretch(1)
        fechar, _botao_fechar = botao_com_atalho("Fechar", "Esc")
        rl.addWidget(fechar)
        layout.addWidget(rodape)


class PaginaRelVendas(_PaginaRelatorioBase):
    """Vendas por Período — faturamento, ticket médio, evolução temporal."""

    ROTULO_PAGINA = "Vendas por Período"


class PaginaRelClientes(_PaginaRelatorioBase):
    """Clientes que Mais Compram — ranking por volume/valor, recência."""

    ROTULO_PAGINA = "Clientes que Mais Compram"


class PaginaRelServicos(_PaginaRelatorioBase):
    """Serviços Mais Executados — frequência, receita por serviço."""

    ROTULO_PAGINA = "Serviços Mais Executados"


class PaginaRelAniversariantes(_PaginaRelatorioBase):
    """Aniversariantes do Mês — lista com contato, faixa etária, envio de parabéns."""

    ROTULO_PAGINA = "Aniversariantes"


__all__ = [
    "PaginaRelatorios",
    "PaginaRelVendas",
    "PaginaRelClientes",
    "PaginaRelServicos",
    "PaginaRelAniversariantes",
]