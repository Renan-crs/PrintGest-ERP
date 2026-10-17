"""Módulo Projetos — Quadro Kanban (PRD Módulo Projetos).

Tela nova do menu "Projetos" sobre o namespace **aditivo** `/v1/projetos`
(Fase 1, núcleo). Substitui o antigo "1 projeto = 1 O.S.": aqui a unidade é o
**cartão**, organizado em **listas** configuráveis (colunas do servidor) — o
mesmo modelo do quadro do Trello.

Camadas:

- **Quadro** (`ui.kanban.QuadroKanban`): as colunas são as listas que vêm de
  `GET /v1/projetos/quadro`; os cartões vêm de `GET /v1/projetos/cartoes`
  (uma consulta com todos os cartões visíveis, agrupados por `lista_id`).
- **Arrastar-e-soltar / menu "Mover para"**: emite o destino e o **índice**
  (0-based) de soltura; a página persiste por `PATCH /cartoes/{id}/mover` com
  `versao` (controle otimista — 409 se outro usuário gravou primeiro).
- **Ficha do cartão** (`DialogoCartao`): criar/editar (título, descrição,
  datas, lembrete, responsável, concluído), arquivar/restaurar e gerenciar
  membros. Membros restringem a visibilidade (PV2) — por isso a ficha mostra
  quem enxerga o cartão.
- **Estrutura do quadro** (`DialogoListas`, Admin/Gerente — PRD §4.1/RN6):
  criar, renomear, arquivar e (só Admin) excluir listas.

RBAC: a tela só é montada para Admin/Gerente/Operador (menu interno). As ações
de estrutura aparecem para gestores; a exclusão definitiva, só para Admin — o
backend reforça as duas (403). Em modo leitura (licença) tudo é somente leitura.

A sincronização com a O.S. e os recursos ricos (etiquetas, checklists,
comentários, anexos) são fases seguintes — ver `docs/revisao_projetos_kanban.md`.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.api import Api
import printgest.core.tarefas as tarefas
from printgest.ui.busca import CampoBusca
from printgest.ui.formulario import (
    CampoArea,
    CampoCheck,
    CampoCombo,
    CampoData,
    CampoTexto,
    data_iso,
    em_volta,
    formatar_data_iso,
)
from printgest.ui.kanban import CartaoKanban, QuadroKanban
from printgest.ui.widgets import ElideLabel, botao_com_atalho

_ORIGENS = {
    "lista": "Lista",
    "manual": "Manual",
    "atribuidor": "Acompanhante",
    "os": "O.S.",
}

# Lembrete em minutos: 0 = sem lembrete; teto de 7 dias (evita valor absurdo).
_LEMBRETE_MAX = 7 * 24 * 60


def _rotulo_origem(origem: str) -> str:
    return _ORIGENS.get(origem, origem)


class DialogoCartao(QDialog):
    """Ficha de um cartão: criar/editar, arquivar/restaurar e membros.

    Emite `salvo` após qualquer gravação bem-sucedida (a página recarrega o
    quadro). Os campos usam os controles do design system (`formulario`) para
    manter o mesmo visual e o mesmo tratamento de "sem data".
    """

    salvo = Signal()

    def __init__(
        self,
        api: Api,
        *,
        modo_leitura: bool = False,
        cartao: dict | None = None,
        listas: list[dict] | None = None,
        usuarios: list[dict] | None = None,
        lista_padrao: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._modo_leitura = modo_leitura
        self._cartao = cartao or {}
        self._criando = not cartao
        self._usuarios = usuarios or []
        self._listas = listas or []

        self.setWindowTitle("Novo cartão" if self._criando else "Editar cartão")
        self.setMinimumWidth(420)

        self._titulo = CampoTexto("Título").obrigatorio()
        self._descricao = CampoArea("Descrição", linhas=4)
        self._lista = CampoCombo(
            "Lista",
            [(l["id"], l["nome"]) for l in self._listas],
            padrao=lista_padrao if lista_padrao is not None else (
                self._listas[0]["id"] if self._listas else None
            ),
        )
        self._data_inicio = CampoData("Início")
        self._data_entrega = CampoData("Entrega")
        self._lembrete = QSpinBox()
        self._lembrete.setRange(0, _LEMBRETE_MAX)
        self._lembrete.setSingleStep(15)
        self._lembrete.setSpecialValueText("Sem lembrete")
        self._lembrete.setSuffix(" min")
        self._responsavel = CampoCombo(
            "Responsável",
            [(0, "— Nenhum —")] + [(u["id"], u["nome"]) for u in self._usuarios],
        )
        self._concluido = CampoCheck("Cartão concluído")

        self._montar()
        self._preencher()

    # ---------------------------------------------------------------- layout

    def _montar(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setSpacing(10)

        raiz.addWidget(em_volta(self._titulo))
        raiz.addWidget(em_volta(self._descricao))

        datas = QHBoxLayout()
        datas.setSpacing(12)
        datas.addWidget(em_volta(self._data_inicio), 1)
        datas.addWidget(em_volta(self._data_entrega), 1)
        raiz.addLayout(datas)

        linha = QHBoxLayout()
        linha.setSpacing(12)
        if self._criando:
            linha.addWidget(em_volta(self._lista), 1)
        linha.addWidget(em_volta(self._responsavel), 1)
        raiz.addLayout(linha)

        lembrete = QWidget()
        col = QVBoxLayout(lembrete)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        rotulo = QLabel("LEMBRETE (ANTECEDÊNCIA)")
        rotulo.setObjectName("labelForm")
        col.addWidget(rotulo)
        col.addWidget(self._lembrete)
        raiz.addWidget(lembrete)

        raiz.addWidget(em_volta(self._concluido))

        # Membros só existem depois que o cartão é gravado (tem id).
        if not self._criando:
            raiz.addWidget(self._montar_membros())

        raiz.addLayout(self._montar_acoes())

        if self._modo_leitura:
            self._somente_leitura()

    def _montar_membros(self) -> QWidget:
        caixa = QWidget()
        col = QVBoxLayout(caixa)
        col.setContentsMargins(0, 4, 0, 0)
        col.setSpacing(6)
        rotulo = QLabel("MEMBROS (RESTRINGEM A VISIBILIDADE)")
        rotulo.setObjectName("labelForm")
        col.addWidget(rotulo)

        self._membros = QListWidget()
        self._membros.setMaximumHeight(110)
        col.addWidget(self._membros)

        linha = QHBoxLayout()
        linha.setSpacing(6)
        self._novo_membro = QComboBox()
        for usuario in self._usuarios:
            self._novo_membro.addItem(usuario["nome"], usuario["id"])
        self._btn_membro = QPushButton("Adicionar")
        self._btn_remover_membro = QPushButton("Remover")
        linha.addWidget(self._novo_membro, 1)
        linha.addWidget(self._btn_membro)
        linha.addWidget(self._btn_remover_membro)
        col.addLayout(linha)

        self._btn_membro.clicked.connect(self._adicionar_membro)
        self._btn_remover_membro.clicked.connect(self._remover_membro)
        return caixa

    def _montar_acoes(self) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(8)
        self._btn_arquivar = QPushButton("Arquivar")
        self._btn_restaurar = QPushButton("Restaurar")
        self._btn_salvar = QPushButton("Salvar")
        self._btn_salvar.setProperty("role", "primary")
        self._btn_fechar = QPushButton("Fechar")

        self._btn_arquivar.clicked.connect(self._arquivar)
        self._btn_restaurar.clicked.connect(self._restaurar)
        self._btn_salvar.clicked.connect(self._salvar)
        self._btn_fechar.clicked.connect(self.reject)

        if self._criando:
            self._btn_arquivar.setVisible(False)
            self._btn_restaurar.setVisible(False)
        else:
            arquivado = bool(self._cartao.get("arquivado"))
            self._btn_arquivar.setVisible(not arquivado)
            self._btn_restaurar.setVisible(arquivado)

        linha.addWidget(self._btn_arquivar)
        linha.addWidget(self._btn_restaurar)
        linha.addStretch(1)
        linha.addWidget(self._btn_fechar)
        linha.addWidget(self._btn_salvar)
        return linha

    # ------------------------------------------------------------- preencher

    def _preencher(self) -> None:
        self._titulo.definir(self._cartao.get("titulo", ""))
        self._descricao.definir(self._cartao.get("descricao", ""))
        self._data_inicio.definir(self._cartao.get("data_inicio"))
        self._data_entrega.definir(self._cartao.get("data_entrega"))
        self._lembrete.setValue(int(self._cartao.get("lembrete_min") or 0))
        self._responsavel.definir(int(self._cartao.get("ultimo_responsavel_id") or 0))
        self._concluido.definir(bool(self._cartao.get("concluido")))
        if not self._criando:
            self._preencher_membros()

    def _preencher_membros(self) -> None:
        self._membros.clear()
        for membro in self._cartao.get("membros") or []:
            texto = f"{membro['nome']} · {_rotulo_origem(membro['origem'])}"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, membro["usuario_id"])
            self._membros.addItem(item)

    def _versao(self) -> int:
        return int(self._cartao.get("versao") or 0)

    # ------------------------------------------------------------- leitura

    def _somente_leitura(self) -> None:
        for campo in (
            self._titulo,
            self._descricao,
            self._data_inicio,
            self._data_entrega,
            self._responsavel,
            self._concluido,
        ):
            campo.habilitar(False)
        self._lembrete.setEnabled(False)
        self._btn_salvar.setEnabled(False)
        self._btn_arquivar.setEnabled(False)
        self._btn_restaurar.setEnabled(False)
        if not self._criando:
            self._btn_membro.setEnabled(False)
            self._btn_remover_membro.setEnabled(False)

    # -------------------------------------------------------------- salvar

    def _salvar(self) -> None:
        titulo = self._titulo.valor()
        if not titulo:
            QMessageBox.warning(self, "Cartão", "Informe o título do cartão.")
            return
        if self._criando:
            self._criar(titulo)
        else:
            self._atualizar(titulo)

    def _criar(self, titulo: str) -> None:
        payload = {
            "lista_id": self._lista.valor(),
            "titulo": titulo,
            "descricao": self._descricao.valor() or None,
            "data_inicio": data_iso(self._data_inicio.valor()),
            "data_entrega": data_iso(self._data_entrega.valor()),
            "lembrete_min": self._lembrete_valor(),
        }
        if payload["lista_id"] is None:
            QMessageBox.warning(self, "Cartão", "Selecione uma lista.")
            return
        tarefas.rodar(
            lambda: self._api.criar_cartao(payload),
            on_ok=self._gravado,
            on_erro=self._falha,
        )

    def _atualizar(self, titulo: str) -> None:
        payload = {
            "versao": self._versao(),
            "titulo": titulo,
            "descricao": self._descricao.valor(),
            "data_inicio": data_iso(self._data_inicio.valor()),
            "data_entrega": data_iso(self._data_entrega.valor()),
            "lembrete_min": self._lembrete_valor(),
            "concluido": self._concluido.valor(),
        }
        alvo = int(self._responsavel.valor() or 0)
        atual = int(self._cartao.get("ultimo_responsavel_id") or 0)

        def _ok(dado: dict) -> None:
            if alvo and alvo != atual:
                tarefas.rodar(
                    lambda: self._api.atribuir_cartao(dado["id"], dado["versao"], alvo),
                    on_ok=self._gravado,
                    on_erro=self._falha,
                )
            else:
                self._gravado(dado)

        tarefas.rodar(
            lambda: self._api.atualizar_cartao(self._cartao["id"], payload),
            on_ok=_ok,
            on_erro=self._falha,
        )

    def _lembrete_valor(self) -> int | None:
        valor = self._lembrete.value()
        return valor or None

    def _gravado(self, dado: dict) -> None:
        self._cartao = dado
        self.salvo.emit()
        self.accept()

    def _falha(self, msg: str) -> None:
        QMessageBox.warning(self, "Não foi possível gravar", msg)

    # ---------------------------------------------------- arquivar/restaurar

    def _arquivar(self) -> None:
        self._acao_versao(self._api.arquivar_cartao, "arquivado", True)

    def _restaurar(self) -> None:
        self._acao_versao(self._api.restaurar_cartao, "arquivado", False)

    def _acao_versao(self, chamada, campo: str, valor: bool) -> None:
        def _ok(dado: dict) -> None:
            self._cartao = dado
            self._cartao[campo] = valor
            self.salvo.emit()
            self.accept()

        tarefas.rodar(
            lambda: chamada(self._cartao["id"], self._versao()),
            on_ok=_ok,
            on_erro=self._falha,
        )

    # --------------------------------------------------------------- membros

    def _adicionar_membro(self) -> None:
        usuario_id = self._novo_membro.currentData()
        if usuario_id is None:
            return
        tarefas.rodar(
            lambda: self._api.adicionar_membro(self._cartao["id"], usuario_id),
            on_ok=self._membros_atualizados,
            on_erro=self._falha,
        )

    def _remover_membro(self) -> None:
        item = self._membros.currentItem()
        if item is None:
            QMessageBox.warning(self, "Membros", "Selecione um membro para remover.")
            return
        usuario_id = item.data(Qt.ItemDataRole.UserRole)
        tarefas.rodar(
            lambda: self._api.remover_membro(self._cartao["id"], usuario_id),
            on_ok=self._membros_atualizados,
            on_erro=self._falha,
        )

    def _membros_atualizados(self, dado: dict) -> None:
        self._cartao = dado
        self._preencher_membros()
        self.salvo.emit()


class DialogoListas(QDialog):
    """Estrutura do quadro: criar/renomear/arquivar/excluir listas (§4.1/RN6).

    Exclusão definitiva é só de Admin (o botão esconde para os demais; o
    backend responde 403 de qualquer forma).
    """

    alterado = Signal()

    def __init__(
        self,
        api: Api,
        *,
        listas: list[dict] | None = None,
        admin: bool = False,
        modo_leitura: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._listas = listas or []
        self._admin = admin
        self._modo_leitura = modo_leitura

        self.setWindowTitle("Listas do quadro")
        self.setMinimumWidth(360)

        raiz = QVBoxLayout(self)
        raiz.setSpacing(10)

        self._lista = QListWidget()
        raiz.addWidget(self._lista, 1)

        self._nome = QLineEdit()
        self._nome.setPlaceholderText("Nome da lista")
        raiz.addWidget(self._nome)

        acoes = QHBoxLayout()
        acoes.setSpacing(6)
        self._btn_nova = QPushButton("Nova")
        self._btn_renomear = QPushButton("Renomear")
        self._btn_arquivar = QPushButton("Arquivar")
        self._btn_excluir = QPushButton("Excluir")
        self._btn_excluir.setProperty("role", "danger")
        self._btn_excluir.setVisible(self._admin)
        self._btn_fechar = QPushButton("Fechar")
        for botao in (
            self._btn_nova,
            self._btn_renomear,
            self._btn_arquivar,
            self._btn_excluir,
        ):
            acoes.addWidget(botao)
        acoes.addStretch(1)
        acoes.addWidget(self._btn_fechar)
        raiz.addLayout(acoes)

        self._btn_nova.clicked.connect(self._nova)
        self._btn_renomear.clicked.connect(self._renomear)
        self._btn_arquivar.clicked.connect(self._arquivar)
        self._btn_excluir.clicked.connect(self._excluir)
        self._btn_fechar.clicked.connect(self.reject)

        if self._modo_leitura:
            for botao in (
                self._btn_nova,
                self._btn_renomear,
                self._btn_arquivar,
                self._btn_excluir,
            ):
                botao.setEnabled(False)
            self._nome.setEnabled(False)

        self._preencher()

    def _preencher(self) -> None:
        self._lista.clear()
        for lista in self._listas:
            item = QListWidgetItem(lista["nome"])
            item.setData(Qt.ItemDataRole.UserRole, lista["id"])
            self._lista.addItem(item)

    def _selecionada(self) -> int | None:
        item = self._lista.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _nova(self) -> None:
        nome = self._nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Listas", "Informe o nome da lista.")
            return
        tarefas.rodar(
            lambda: self._api.criar_lista({"nome": nome}),
            on_ok=self._ok,
            on_erro=self._falha,
        )

    def _renomear(self) -> None:
        lista_id = self._selecionada()
        nome = self._nome.text().strip()
        if lista_id is None:
            QMessageBox.warning(self, "Listas", "Selecione uma lista.")
            return
        if not nome:
            QMessageBox.warning(self, "Listas", "Informe o novo nome da lista.")
            return
        tarefas.rodar(
            lambda: self._api.atualizar_lista(lista_id, {"nome": nome}),
            on_ok=self._ok,
            on_erro=self._falha,
        )

    def _arquivar(self) -> None:
        lista_id = self._selecionada()
        if lista_id is None:
            QMessageBox.warning(self, "Listas", "Selecione uma lista.")
            return
        tarefas.rodar(
            lambda: self._api.arquivar_lista(lista_id),
            on_ok=self._ok,
            on_erro=self._falha,
        )

    def _excluir(self) -> None:
        lista_id = self._selecionada()
        if lista_id is None:
            QMessageBox.warning(self, "Listas", "Selecione uma lista.")
            return
        resposta = QMessageBox.question(
            self,
            "Excluir lista",
            "Excluir definitivamente esta lista? Só é possível se estiver vazia.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        tarefas.rodar(
            lambda: self._api.excluir_lista(lista_id),
            on_ok=lambda _d: self._ok({}),
            on_erro=self._falha,
        )

    def _ok(self, _dado: dict) -> None:
        self._nome.clear()
        self._recarregar()
        self.alterado.emit()

    def _falha(self, msg: str) -> None:
        QMessageBox.warning(self, "Não foi possível alterar", msg)

    def _recarregar(self) -> None:
        dado = self._api.obter_quadro()
        if isinstance(dado, dict):
            self._listas = dado.get("listas") or []
        self._preencher()


class PaginaProjetos(QWidget):
    """Página "Projetos": quadro Kanban servido por `/v1/projetos`."""

    LUGAR_BUSCA = "Buscar por título ou descrição do cartão..."

    def __init__(
        self,
        api: Api,
        modo_leitura: bool = False,
        nivel: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._modo_leitura = modo_leitura
        self._nivel = nivel
        self._gestor = nivel in ("admin", "gerente")
        self._admin = nivel == "admin"

        self._seq = 0
        self._listas: list[dict] = []
        self._cartoes: dict[int, dict] = {}
        self._usuarios: list[dict] = []

        self._montar()
        self._carregar_usuarios()
        self.recarregar()

    # ------------------------------------------------------------ construção

    def _montar(self) -> None:
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(10)
        raiz.addWidget(self._barra_titulo())
        raiz.addWidget(self._barra_busca())

        self._quadro = QuadroKanban([], self._cartao)
        self._quadro.selecionado.connect(self._abrir_cartao)
        self._quadro.movido.connect(self._mover)
        self._quadro.permitir_movimento(not self._modo_leitura)
        raiz.addWidget(self._quadro, 1)

        self._vazio = QLabel(
            "O quadro ainda não tem listas. Um gestor pode criar a primeira."
        )
        self._vazio.setProperty("role", "muted")
        self._vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vazio.setVisible(False)
        raiz.addWidget(self._vazio)

    def _barra_titulo(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)

        titulo = ElideLabel("Projetos")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo, 1)

        self._btn_listas = QPushButton("Listas")
        self._btn_listas.setVisible(self._gestor)
        self._btn_listas.clicked.connect(self._gerenciar_listas)
        linha.addWidget(self._btn_listas)

        atualizar, self._btn_atualizar = botao_com_atalho("Atualizar", "")
        self._btn_atualizar.clicked.connect(
            lambda: self.recarregar(self._busca.texto())
        )
        linha.addWidget(atualizar)

        novo, self._btn_novo = botao_com_atalho("Novo Cartão", "F6", "primary")
        self._btn_novo.clicked.connect(self._novo_cartao)
        linha.addWidget(novo)

        if self._modo_leitura:
            self._btn_novo.setEnabled(False)
        return caixa

    def _barra_busca(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        self._busca = CampoBusca(self.LUGAR_BUSCA)
        self._busca.buscado.connect(lambda q: self.recarregar(q))
        linha.addWidget(self._busca, 1)
        return caixa

    # ---------------------------------------------------------------- dados

    def _carregar_usuarios(self) -> None:
        catalogos.carregar(
            "usuarios",
            lambda: self._api.listar("usuarios", limit=200),
            on_ok=self._usuarios_recebidos,
        )

    def _usuarios_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", []) if isinstance(saida, dict) else []
        self._usuarios = [
            {"id": u["id"], "nome": u.get("nome") or u.get("login") or "Usuário"}
            for u in dados
            if isinstance(u, dict) and u.get("id") is not None
        ]

    def recarregar(self, q: str = "") -> None:
        """Busca quadro + cartões (uma consulta) e desenha quando ambos chegam."""
        self._seq += 1
        seq = self._seq
        estado: dict = {}
        pendentes = [2]

        def _pronto() -> None:
            if seq != self._seq:
                return
            pendentes[0] -= 1
            if pendentes[0] == 0:
                self._aplicar(estado)

        def _ok_quadro(quadro) -> None:
            if seq != self._seq:
                return
            estado["quadro"] = quadro if isinstance(quadro, dict) else {}
            _pronto()

        def _ok_cartoes(saida) -> None:
            if seq != self._seq:
                return
            estado["cartoes"] = saida.get("data", []) if isinstance(saida, dict) else []
            _pronto()

        def _falha(msg: str) -> None:
            if seq == self._seq:
                self._erro(msg)

        tarefas.rodar(self._api.obter_quadro, _ok_quadro, _falha)
        tarefas.rodar(lambda: self._api.listar_cartoes(q=q), _ok_cartoes, _falha)

    def _aplicar(self, estado: dict) -> None:
        quadro = estado.get("quadro") or {}
        self._listas = quadro.get("listas") or []

        colunas = [(str(l["id"]), l["nome"]) for l in self._listas]
        if colunas != self._quadro.rotulos:
            self._quadro.definir_colunas(colunas)
            self._quadro.permitir_movimento(not self._modo_leitura)

        self._cartoes = {c["id"]: c for c in estado.get("cartoes", [])}
        por_coluna: dict[str, list[dict]] = {str(l["id"]): [] for l in self._listas}
        for cartao in self._cartoes.values():
            chave = str(cartao.get("lista_id"))
            if chave in por_coluna:
                por_coluna[chave].append(cartao)
        for itens in por_coluna.values():
            itens.sort(key=lambda c: float(c.get("posicao") or 0))
        self._quadro.preencher(por_coluna)

        self._vazio.setVisible(not self._listas)
        self._quadro.setVisible(bool(self._listas))

    # ---------------------------------------------------------------- cartão

    def _cartao(self, dado: dict) -> CartaoKanban:
        responsavel = dado.get("ultimo_responsavel_nome")
        membros = [m["nome"] for m in (dado.get("membros") or []) if m.get("nome")]
        if responsavel:
            subtitulo = f"→ {responsavel}"
        elif membros:
            subtitulo = ", ".join(membros[:3])
        else:
            subtitulo = "Equipe"

        prazo = formatar_data_iso(dado.get("data_entrega"))
        if dado.get("concluido"):
            rodape = f"Concluído · {prazo}" if prazo else "Concluído"
        else:
            rodape = prazo or "Sem prazo"

        return CartaoKanban(
            dado.get("id"),
            dado.get("titulo") or "Sem título",
            subtitulo,
            rodape,
            atrasado=self._atrasado(dado),
        )

    def _atrasado(self, dado: dict) -> bool:
        if dado.get("concluido") or dado.get("arquivado"):
            return False
        prazo = dado.get("data_entrega")
        if not prazo:
            return False
        try:
            return date.fromisoformat(str(prazo)[:10]) < date.today()
        except ValueError:
            return False

    # ---------------------------------------------------------------- mover

    def _mover(self, item_id, chave_destino: str, indice: int) -> None:
        if self._modo_leitura:
            QMessageBox.warning(
                self,
                "Modo leitura",
                "A licença está em modo leitura; não é possível mover cartões.",
            )
            self.recarregar(self._busca.texto())
            return

        cartao = self._cartoes.get(item_id)
        if cartao is None:
            return
        origem = self._quadro.coluna_do(item_id)
        if origem is None:
            return
        coluna_destino = (
            self._quadro.coluna(chave_destino)
            if self._quadro.tem_coluna(chave_destino)
            else None
        )
        if coluna_destino is None:
            return

        indice = self._indice_efetivo(item_id, origem, chave_destino, indice)
        if origem == chave_destino and indice == self._indice_atual(item_id, chave_destino):
            return  # solto na própria posição: nada a fazer

        payload = {
            "versao": int(cartao.get("versao") or 0),
            "lista_id": int(chave_destino),
            "posicao": indice,
        }
        tarefas.rodar(
            lambda: self._api.mover_cartao(item_id, payload),
            on_ok=lambda _d: self.recarregar(self._busca.texto()),
            on_erro=self._erro_mover,
        )

    def _indice_atual(self, item_id, chave: str) -> int:
        cartoes = [c.id_registro for c in self._quadro.coluna(chave).cartoes()]
        return cartoes.index(item_id) if item_id in cartoes else -1

    def _indice_efetivo(self, item_id, origem: str, destino: str, indice: int) -> int:
        """Ajusta o índice de soltura para a semântica do servidor (sem o próprio).

        Ao reordenar dentro da mesma lista, o cartão é removido antes de calcular
        a fração; se ele estava antes do ponto de soltura, o índice cai 1. O menu
        de contexto envia -1 (anexar ao final).
        """
        if indice < 0:
            return len(self._quadro.coluna(destino).cartoes())
        if origem == destino:
            atual = self._indice_atual(item_id, destino)
            if atual >= 0 and atual < indice:
                return indice - 1
        return indice

    def _erro_mover(self, msg: str) -> None:
        QMessageBox.warning(self, "Não foi possível mover", msg)
        self.recarregar(self._busca.texto())

    # ---------------------------------------------------------- ficha cartão

    def _novo_cartao(self) -> None:
        if self._modo_leitura:
            return
        if not self._listas:
            QMessageBox.information(
                self, "Projetos", "Crie uma lista antes de adicionar cartões."
            )
            return
        self._abrir_dialogo(
            DialogoCartao(
                self._api,
                modo_leitura=self._modo_leitura,
                listas=self._listas,
                usuarios=self._usuarios,
                parent=self,
            )
        )

    def _abrir_cartao(self, item_id) -> None:
        cartao = self._cartoes.get(item_id)
        if cartao is None:
            return
        self._abrir_dialogo(
            DialogoCartao(
                self._api,
                modo_leitura=self._modo_leitura,
                cartao=cartao,
                listas=self._listas,
                usuarios=self._usuarios,
                parent=self,
            )
        )

    def _abrir_dialogo(self, dialogo: QDialog) -> None:
        dialogo.salvo.connect(lambda: self.recarregar(self._busca.texto()))
        self._dialogo = dialogo
        dialogo.exec()

    # --------------------------------------------------------------- listas

    def _gerenciar_listas(self) -> None:
        dialogo = DialogoListas(
            self._api,
            listas=self._listas,
            admin=self._admin,
            modo_leitura=self._modo_leitura,
            parent=self,
        )
        dialogo.alterado.connect(lambda: self.recarregar(self._busca.texto()))
        self._dialogo_listas = dialogo
        dialogo.exec()

    # ---------------------------------------------------------------- erros

    def _erro(self, msg: str) -> None:
        QMessageBox.warning(self, "Falha ao carregar projetos", msg)
