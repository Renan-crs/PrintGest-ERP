"""Módulo Movimento — Ordem de Serviço (mockup 3.1/3.2) e Orçamentos (3.3).

Ordem de serviço e orçamento vivem na mesma rota `/v1/os`, diferenciados por
`tipo`. A página é a mesma base `PaginaCrud` com `TIPO` fixo; a subclasse de
orçamento troca rótulos e adiciona a ação de conversão (`POST /{id}/converter`).
O avanço de status usa `PATCH /{id}/status` e o cancelamento `DELETE /{id}`.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.dominio import FORMAS_PAGAMENTO
from printgest.core.tarefas import rodar
from printgest.ui.formulario import (
    CampoArea,
    CampoCheck,
    CampoCombo,
    CampoData,
    CampoValor,
    data_iso,
    formatar_data_iso,
    formatar_moeda,
    limpo,
)
from printgest.ui.grade_itens import GradeItens
from printgest.ui.kanban import CartaoKanban, QuadroKanban
from printgest.ui.modulos.condicao_pagamento import CondicaoPagamentoCliente
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.paginador import LOTE
from printgest.ui.widgets import botao_com_atalho

_PROXIMO_STATUS = {
    "aberto": "aprovado",
    "aprovado": "producao",
    "producao": "pronta",
    "pronta": "entregue",
}

# Etapas do quadro de Projetos. "Aguardando" agrupa `aberto` e `aprovado` — o
# orçamento aprovado ainda não entrou em produção (ver docs/revisao_projetos.md).
_COLUNAS_QUADRO = [
    ("aguardando", "Aguardando", ("aberto", "aprovado")),
    ("producao", "Em produção", ("producao",)),
    ("pronta", "Prontas", ("pronta",)),
    ("entregue", "Entregues", ("entregue",)),
]


class PaginaOS(CondicaoPagamentoCliente, PaginaCrud):
    ENTIDADE = "os"
    TIPO = "os"
    ROTULO_PAGINA = "Gestão de Ordens de Serviço (O.S.)"
    ROTULO_NOVO = "Nova Ordem de Serviço"
    GRUPO_LISTA = "FILA OPERACIONAL"
    LUGAR_BUSCA = "Buscar por Nº da O.S. ou nome do cliente..."
    CAMPO_NOME = "cliente_nome"
    CHAVES = ["id", "numero", "cliente_nome", "status", "data_previsao_entrega", "valor_total"]
    COLUNAS = ["O.S.", "Nº", "Cliente", "Status", "Prazo", "Total"]
    CHAVE_FILTRO = "status"
    FILTROS = [
        ("", "Todas"),
        ("aberto", "Abertas"),
        ("aprovado", "Aprovadas"),
        ("producao", "Em Produção"),
        ("pronta", "Prontas"),
        ("entregue", "Entregues"),
    ]

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._carregar_clientes_flags()
        self._carregar_funcionarios()

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._iniciar_condicao_pagamento()  # flags de pagamento por cliente
        self._cliente = CampoCombo("Cliente", []).obrigatorio()
        self._vendedor = CampoCombo("Vendedor", [])
        self._atendente = CampoCombo("Atendente", [])
        self._previsao = CampoData("Previsão de Entrega")
        self._forma = CampoCombo("Forma de Pagamento", FORMAS_PAGAMENTO)
        self._desconto = CampoValor("Desconto")
        self._obs = CampoArea("Observações", linhas=2)
        self._pagamento_confirmado = CampoCheck(
            "Pagamento já recebido"
        )
        self._itens = GradeItens("", api=self._api)
        return [
            ("Cliente & Equipe", [self._cliente, self._vendedor, self._atendente]),
            (
                "Prazos & Financeiro",
                [
                    self._previsao,
                    self._forma,
                    self._desconto,
                    self._obs,
                    self._pagamento_confirmado,
                ],
            ),
            ("Itens", [self._itens]),
        ]

    def _conectar_campos(self) -> None:
        self._cliente.widget.currentIndexChanged.connect(self._cliente_mudou)

    def _padroes_do_form(self) -> None:
        self._desconto.definir(None)
        self._pagamento_confirmado.definir(False)
        self._cliente_mudou()

    # ---------------------------------------------------------------- busca

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        return self._api.listar_os(
            q=q, status=self._filtro or None, tipo=self.TIPO, limit=LOTE, offset=offset
        )

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "status":
            return str(dado.get("status", "")).upper()
        if chave == "valor_total":
            return formatar_moeda(dado.get("valor_total"))
        if chave == "data_previsao_entrega":
            return formatar_data_iso(dado.get("data_previsao_entrega"))
        return super()._formatar_texto(dado, chave)

    # ------------------------------------------------------------ carregar

    def _carregar_funcionarios(self) -> None:
        catalogos.carregar(
            "funcionarios",
            lambda: self._api.listar("funcionarios", limit=1000),
            on_ok=self._funcionarios_recebidos,
        )

    def _funcionarios_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", [])
        vendedores = [r for r in dados if r.get("e_vendedor")] or dados
        atendentes = [r for r in dados if r.get("e_atendente")] or dados
        self._vendedor.alterar_opcoes([(r["id"], r["nome"]) for r in vendedores])
        self._atendente.alterar_opcoes([(r["id"], r["nome"]) for r in atendentes])

    def _preencher_campos(self, dado: dict) -> None:
        self._cliente.definir(dado.get("cliente_id"))
        self._vendedor.definir(dado.get("vendedor_id"))
        self._atendente.definir(dado.get("atendente_id"))
        self._previsao.definir(dado.get("data_previsao_entrega"))
        self._forma.definir(dado.get("forma_pagamento"))
        self._desconto.definir(dado.get("desconto"))
        self._obs.definir(dado.get("observacoes"))
        self._pagamento_confirmado.definir(False)
        self._itens.definir(dado.get("itens") or [])

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._cliente.valor():
            return ("Informe o cliente.", self._cliente)
        if not self._itens.valor():
            return ("Adicione ao menos um item.", self._itens.widget)
        if self._editando_id is None and self.TIPO == "os":
            exigencia = self._exigencia_pendente()
            if exigencia:
                return (
                    f"O cliente exige {exigencia}. Marque 'Pagamento já recebido' "
                    "para lançar a O.S.",
                    self._pagamento_confirmado,
                )
        return None

    def _payload(self) -> dict:
        return {
            "tipo": self.TIPO,
            "cliente_id": self._cliente.valor(),
            "vendedor_id": self._vendedor.valor(),
            "atendente_id": self._atendente.valor(),
            "data_previsao_entrega": data_iso(self._previsao.valor()),
            "desconto": str(self._desconto.valor() or "0"),
            "forma_pagamento": self._forma.valor(),
            "observacoes": limpo(self._obs.valor()),
            "pagamento_confirmado": self._pagamento_confirmado.valor(),
            "itens": self._itens.valor(),
        }

    # ------------------------------------------------------- ações de status

    def _acao_extra(self):
        avancar, self._btn_avancar = botao_com_atalho("Avançar Status", "F7")
        self._btn_avancar.clicked.connect(self._avancar_status)
        cancelar, self._btn_cancelar_os = botao_com_atalho("Cancelar O.S.", "F8")
        self._btn_cancelar_os.clicked.connect(self._cancelar_os)
        return [avancar, cancelar]

    def _selecionado_ou_aviso(self, titulo: str, msg: str) -> dict | None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(self, titulo, msg)
        return dado

    def _avancar_status(self) -> None:
        dado = self._selecionado_ou_aviso(
            "O.S.", "Selecione uma ordem de serviço na lista."
        )
        if not dado:
            return
        proximo = _PROXIMO_STATUS.get(dado.get("status"))
        if proximo is None:
            QMessageBox.information(
                self, "O.S.", "Registro sem próxima etapa (entregue/cancelado)."
            )
            return
        item_id = dado["id"]
        self._btn_avancar.setEnabled(False)  # trava contra duplo PATCH
        rodar(
            lambda: self._api.atualizar_status(item_id, proximo),
            on_ok=self._status_avancado,
            on_erro=self._status_avancado_erro,
        )

    def _status_avancado(self, _dado: dict) -> None:
        self._btn_avancar.setEnabled(True)
        self.recarregar(self._busca.texto())

    def _status_avancado_erro(self, msg: str) -> None:
        self._btn_avancar.setEnabled(True)
        self._erro_salvar(msg)

    def _cancelar_os(self) -> None:
        dado = self._selecionado_ou_aviso(
            self.ROTULO_PAGINA, "Selecione um registro na lista."
        )
        if not dado:
            return
        resposta = QMessageBox.question(
            self,
            "Cancelar registro",
            f"Cancelar o registro Nº {dado.get('numero')}?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        item_id = dado["id"]
        rodar(
            lambda: self._api.excluir(self.ENTIDADE, item_id),
            on_ok=lambda _out: self.recarregar(self._busca.texto()),
            on_erro=lambda msg: self._erro_salvar(msg),
        )


class PaginaOrcamento(PaginaOS):
    TIPO = "orcamento"
    ROTULO_PAGINA = "Orçamentos Gráficos & Simulações"
    ROTULO_NOVO = "Novo Orçamento"
    GRUPO_LISTA = "SIMULAÇÕES DE PREÇO"
    FILTROS = [
        ("", "Todos"),
        ("aberto", "Abertos"),
        ("convertido", "Convertidos"),
        ("cancelado", "Cancelados"),
    ]

    def _acao_extra(self):
        converter, self._btn_converter = botao_com_atalho(
            "Converter em O.S.", "F9", "primary"
        )
        self._btn_converter.clicked.connect(self._converter_em_os)
        cancelar, self._btn_cancelar_os = botao_com_atalho("Cancelar Orçamento", "F8")
        self._btn_cancelar_os.clicked.connect(self._cancelar_os)
        return [converter, cancelar]

    def _converter_em_os(self) -> None:
        dado = self._selecionado_ou_aviso(
            "Orçamentos", "Selecione um orçamento na lista."
        )
        if not dado:
            return
        exigencia = self._exigencia_do_cliente(dado.get("cliente_id"))
        confirmado = False
        if exigencia:
            resposta = QMessageBox.question(
                self,
                "Converter em O.S.",
                f"O cliente exige {exigencia}.\nConfirmar o recebimento e converter "
                f"o orçamento Nº {dado.get('numero')} em ordem de serviço?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
            confirmado = True
        else:
            resposta = QMessageBox.question(
                self,
                "Converter em O.S.",
                f"Converter o orçamento Nº {dado.get('numero')} em ordem de serviço?",
            )
            if resposta != QMessageBox.StandardButton.Yes:
                return
        item_id = dado["id"]
        rodar(
            lambda: self._api.acao(
                "os", item_id, "converter", {"pagamento_confirmado": confirmado}
            ),
            on_ok=self._convertido,
            on_erro=lambda msg: self._erro_salvar(msg),
        )

    def _convertido(self, dados: dict) -> None:
        self.recarregar(self._busca.texto())
        QMessageBox.information(
            self,
            "Ordem de Serviço gerada",
            f"Orçamento convertido na O.S. Nº {dados.get('numero')}.",
        )


class PaginaProjetos(PaginaOS):
    """Menu "Projetos" (v2.1 §1): 1 projeto = 1 O.S. (tipo `os`).

    Duas visões sobre o mesmo cadastro de O.S.:

    - **Quadro** (Kanban): colunas por etapa, cartões clicáveis. Clicar num
      cartão abre o registro na visão Lista (o formulário é o mesmo de O.S.).
    - **Lista**: grade densa + formulário lateral, como no restante do sistema.

    O calendário e o arrastar-e-soltar entre colunas ficam para a fase 3 do
    roadmap (ver `docs/revisao_projetos.md`) — aqui o quadro é somente leitura.
    """

    ROTULO_PAGINA = "Projetos"
    ROTULO_NOVO = "Novo Projeto"
    GRUPO_LISTA = "PROJETOS (1 PROJETO = 1 O.S.)"
    LUGAR_BUSCA = "Buscar por Nº do projeto ou nome do cliente..."
    CHAVES = ["numero", "cliente_nome", "status", "data_previsao_entrega", "valor_total"]
    COLUNAS = ["Nº", "Cliente", "Status", "Prazo", "Total"]

    _seq_quadro = 0

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._montar_quadro()

    # --------------------------------------------------------------- visões

    def _badges_barra(self) -> list:
        """Alternador Quadro/Lista, anexado à barra de título."""
        self._visao = QWidget()
        linha = QHBoxLayout(self._visao)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        self._btn_quadro = QPushButton("Quadro")
        self._btn_lista = QPushButton("Lista")
        for botao in (self._btn_quadro, self._btn_lista):
            botao.setObjectName("chaveRapida")
            botao.setCheckable(True)
            linha.addWidget(botao)
        self._btn_quadro.setChecked(True)
        self._btn_quadro.clicked.connect(lambda: self._trocar_visao(0))
        self._btn_lista.clicked.connect(lambda: self._trocar_visao(1))
        return [self._visao]

    def _montar_quadro(self) -> None:
        self._quadro = QuadroKanban(
            [(chave, rotulo) for chave, rotulo, _s in _COLUNAS_QUADRO],
            fabrica=self._cartao,
        )
        self._quadro.selecionado.connect(self._abrir_registro)

        raiz = self.layout()
        # Troca a "lista + formulário" pelo quadro e vice-versa. Um
        # `QStackedWidget` inflaria o piso da tela com a página oculta; trocar o
        # widget central mantém o piso apenas do que está visível.
        self._divisor = raiz.itemAt(2).widget()  # [0] título, [1] busca, [2] main
        raiz.removeWidget(self._divisor)
        self._divisor.hide()
        self._main_atual = self._divisor
        self._visao_atual = 1
        self._trocar_visao(0)

    def _trocar_visao(self, indice: int) -> None:
        alvo = self._quadro if indice == 0 else self._divisor
        if alvo is not self._main_atual:
            raiz = self.layout()
            raiz.removeWidget(self._main_atual)
            self._main_atual.hide()
            raiz.addWidget(alvo, 1)
            alvo.show()
            self._main_atual = alvo
        self._visao_atual = indice
        self._btn_quadro.setChecked(indice == 0)
        self._btn_lista.setChecked(indice == 1)
        # Os filtros de status são da Lista; no Quadro as colunas já são os status.
        if self._filtros_widget is not None:
            self._filtros_widget.setVisible(indice == 1)
        if indice == 0:
            self._atualizar_quadro(self._busca.texto())

    def _novo(self) -> None:
        # O formulário vive na visão Lista; criar exige vê-lo.
        self._trocar_visao(1)
        super()._novo()

    def recarregar(self, q: str = "", offset: int | None = None) -> None:
        super().recarregar(q, offset)
        if getattr(self, "_quadro", None) is not None:
            self._atualizar_quadro(q or "")

    # ----------------------------------------------------------------- quadro

    def _cartao(self, dado: dict) -> CartaoKanban:
        prazo = formatar_data_iso(dado.get("data_previsao_entrega")) or "Sem prazo"
        total = formatar_moeda(dado.get("valor_total")) or "R$ 0,00"
        return CartaoKanban(
            dado.get("id"),
            f"Projeto Nº {dado.get('numero')}",
            dado.get("cliente_nome") or "Consumidor final",
            f"{prazo} · {total}",
            atrasado=self._atrasado(dado),
        )

    def _atrasado(self, dado: dict) -> bool:
        if dado.get("status") in ("entregue", "cancelado"):
            return False
        prazo = dado.get("data_previsao_entrega")
        if not prazo:
            return False
        try:
            return date.fromisoformat(str(prazo)[:10]) < date.today()
        except ValueError:
            return False

    def _atualizar_quadro(self, q: str = "") -> None:
        self._seq_quadro += 1
        seq = self._seq_quadro
        acumulado: dict[str, list[dict]] = {}
        pendentes = [len(_COLUNAS_QUADRO)]
        for chave, _rotulo, status_etapas in _COLUNAS_QUADRO:
            rodar(
                lambda etapas=status_etapas: self._buscar_etapa(q, etapas),
                on_ok=self._etapa_recebida(seq, chave, acumulado, pendentes),
                on_erro=self._etapa_falhou(seq, chave, acumulado, pendentes),
            )

    def _buscar_etapa(self, q: str, status_etapas: tuple) -> list[dict]:
        itens: list[dict] = []
        for status in status_etapas:
            saida = self._api.listar_os(q=q, status=status, tipo=self.TIPO, limit=200)
            itens.extend(saida.get("data", []))
        itens.sort(key=lambda o: o.get("numero") or 0, reverse=True)
        return itens

    def _etapa_recebida(self, seq: int, chave: str, acumulado: dict, pendentes: list):
        def _aplicar(itens: list[dict]) -> None:
            if seq != self._seq_quadro:
                return
            acumulado[chave] = itens
            pendentes[0] -= 1
            if pendentes[0] == 0:
                self._quadro.preencher(acumulado)

        return _aplicar

    def _etapa_falhou(self, seq: int, chave: str, acumulado: dict, pendentes: list):
        def _aplicar(_msg: str) -> None:
            # Falha de uma coluna não derruba o quadro: ela fica vazia e as
            # demais seguem na tela.
            self._etapa_recebida(seq, chave, acumulado, pendentes)([])

        return _aplicar

    # ----------------------------------------------------------- abrir cartão

    def _abrir_registro(self, item_id) -> None:
        self._trocar_visao(1)
        for linha in range(self._tabela.rowCount()):
            item = self._tabela.item(linha, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole + 1) == item_id:
                self._tabela.selectRow(linha)
                return
        # Registro fora da página atual: busca e mostra direto no formulário.
        rodar(
            lambda: self._api.obter(self.ENTIDADE, item_id),
            on_ok=self._carregar_no_form,
            on_erro=lambda msg: self._erro_carga(msg),
        )
