"""Módulo Movimento — Ordem de Serviço (mockup 3.1/3.2) e Orçamentos (3.3).

Ordem de serviço e orçamento vivem na mesma rota `/v1/os`, diferenciados por
`tipo`. A página é a mesma base `PaginaCrud` com `TIPO` fixo; a subclasse de
orçamento troca rótulos e adiciona a ação de conversão (`POST /{id}/converter`).
O avanço de status usa `PATCH /{id}/status` e o cancelamento `DELETE /{id}`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from printgest.core import catalogos
from printgest.core.dominio import FORMAS_PAGAMENTO
from printgest.core.dominio.ordem_servico import (
    _PROXIMO_STATUS,
    _rotulo_status,
)
import printgest.core.tarefas as tarefas
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
from printgest.ui.modulos.condicao_pagamento import CondicaoPagamentoCliente
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.paginador import LOTE
from printgest.ui.widgets import botao_com_atalho


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
        ("producao", "Em Produção"),
        ("pronta", "Prontas"),
        ("entregue", "Entregues"),
        ("cancelado", "Canceladas"),
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
        cancelar, self._btn_cancelar_os = botao_com_atalho("Cancelar Projeto", "F8", "danger")
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
        atual = dado.get("status")
        proximo = _PROXIMO_STATUS.get(atual)
        if proximo is None:
            QMessageBox.information(
                self, "O.S.", "Registro sem próxima etapa (entregue/cancelado)."
            )
            return
        # Atualiza o texto do botão para mostrar o destino
        self._btn_avancar.setText(f"Avançar para {_rotulo_status(proximo)}")
        item_id = dado["id"]
        self._btn_avancar.setEnabled(False)  # trava contra duplo PATCH
        tarefas.rodar(
            lambda: self._api.atualizar_status(item_id, proximo),
            on_ok=self._status_avancado,
            on_erro=self._status_avancado_erro,
        )

    def _status_avancado(self, _dado: dict) -> None:
        self._btn_avancar.setEnabled(True)
        self._btn_avancar.setText("Avançar Status")
        self.recarregar(self._busca.texto())

    def _status_avancado_erro(self, msg: str) -> None:
        self._btn_avancar.setEnabled(True)
        self._btn_avancar.setText("Avançar Status")
        self._erro_salvar(msg)

    def _cancelar_os(self) -> None:
        dado = self._selecionado_ou_aviso(
            self.ROTULO_PAGINA, "Selecione um registro na lista."
        )
        if not dado:
            return
        resposta = QMessageBox.question(
            self,
            "Cancelar Projeto",
            f"Cancelar permanentemente o projeto Nº {dado.get('numero')}?\n"
            "Esta ação não pode ser desfeita.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        item_id = dado["id"]
        tarefas.rodar(
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
        tarefas.rodar(
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
