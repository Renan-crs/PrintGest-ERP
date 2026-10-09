"""Módulo Movimento — Venda de Balcão / PDV (mockup 3.4) sobre a base `PaginaCrud`.

Vendas são imutáveis na API (`POST /v1/vendas` cria, `DELETE /{id}` cancela,
não há PUT). A página monta o "cupom" à direita (itens + destinatário +
condições) e lista os lançamentos à esquerda, com filtro por status.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from printgest.core import catalogos
from printgest.core.dominio import FORMAS_PAGAMENTO
from printgest.core.tarefas import rodar
from printgest.ui.formulario import (
    CampoArea,
    CampoCombo,
    CampoTexto,
    CampoValor,
    formatar_data_iso,
    formatar_moeda,
)
from printgest.ui.grade_itens import GradeItens
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.paginador import LOTE
from printgest.ui.widgets import botao_com_atalho


class PaginaVendaBalcao(PaginaCrud):
    ENTIDADE = "vendas"
    ROTULO_PAGINA = "Venda Balcão / PDV"
    ROTULO_NOVO = "Nova Venda de Balcão"
    GRUPO_LISTA = "CUPOM DE BALCÃO"
    LUGAR_BUSCA = "Buscar por Nº da venda ou cliente..."
    CAMPO_NOME = "cliente_nome"
    CHAVES = ["numero", "cliente_nome", "forma_pagamento", "valor_total", "status", "data_venda"]
    COLUNAS = ["Nº", "Cliente", "Pagamento", "Total", "Status", "Data"]
    CHAVE_FILTRO = "status"
    FILTROS = [
        ("", "Todas"),
        ("ok", "Vendas"),
        ("cancelado", "Canceladas"),
    ]

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._carregar_clientes()
        self._carregar_vendedores()

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._cliente = CampoCombo("Cliente", [])
        self._vendedor = CampoCombo("Vendedor", [])
        self._forma = CampoCombo("Forma de Pagamento", FORMAS_PAGAMENTO).obrigatorio()
        self._parcelas = CampoTexto("Parcelas", valor="1", maximo=2)
        self._desconto = CampoValor("Desconto")
        self._obs = CampoArea("Observações", linhas=2)
        self._itens = GradeItens("Itens do Cupom", api=self._api)
        return [
            ("Cliente & Condições", [self._cliente, self._vendedor, self._forma, self._parcelas, self._desconto, self._obs]),
            ("Itens do Cupom", [self._itens]),
        ]

    def _padroes_do_form(self) -> None:
        self._parcelas.definir("1")
        self._desconto.definir(None)

    # ---------------------------------------------------------------- busca

    def recarregar(self, q: str = "", offset: int | None = None) -> None:
        if offset is None:
            offset = self._offset
        rodar(
            lambda: self._api.listar_vendas(
                q=q, status_venda=self._filtro or None, limit=LOTE, offset=offset
            ),
            on_ok=lambda out: self._recebidos(q, offset, out),
            on_erro=lambda msg: self._erro_carga(msg),
        )

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "id":
            ident = dado.get("id")
            return f"#{ident:05d}" if isinstance(ident, int) else ""
        if chave == "forma_pagamento":
            return str(dado.get("forma_pagamento", "")).upper()
        if chave == "status":
            return str(dado.get("status", "")).upper()
        if chave == "valor_total":
            return formatar_moeda(dado.get("valor_total"))
        if chave == "data_venda":
            return formatar_data_iso(dado.get("data_venda"))
        return super()._formatar_texto(dado, chave)

    # ------------------------------------------------------------ carregar

    def _carregar_clientes(self) -> None:
        catalogos.carregar(
            "clientes",
            lambda: self._api.listar("clientes", limit=1000),
            on_ok=self._clientes_recebidos,
        )

    def _clientes_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", [])
        self._cliente.alterar_opcoes([(r["id"], r["nome_razao"]) for r in dados])

    def _carregar_vendedores(self) -> None:
        catalogos.carregar(
            "funcionarios",
            lambda: self._api.listar("funcionarios", limit=1000),
            on_ok=self._vendedores_recebidos,
        )

    def _vendedores_recebidos(self, saida: dict) -> None:
        dados = saida.get("data", [])
        vendedores = [r for r in dados if r.get("e_vendedor")] or dados
        self._vendedor.alterar_opcoes([(r["id"], r["nome"]) for r in vendedores])

    def _preencher_campos(self, dado: dict) -> None:
        self._cliente.definir(dado.get("cliente_id"))
        self._vendedor.definir(dado.get("vendedor_id"))
        self._forma.definir(dado.get("forma_pagamento"))
        self._parcelas.definir(str(dado.get("parcelas") or 1))
        self._desconto.definir(dado.get("desconto"))
        self._obs.definir(dado.get("observacoes"))
        self._itens.definir(dado.get("itens") or [])

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._forma.valor():
            return ("Informe a forma de pagamento.", self._forma)
        parcelas = (self._parcelas.valor() or "").strip()
        if not parcelas.isdigit() or int(parcelas) < 1:
            return ("Parcelas deve ser um número maior que zero.", self._parcelas)
        if not self._itens.valor():
            return ("Adicione ao menos um item ao cupom.", self._itens.widget)
        return None

    def _payload(self) -> dict:
        parcelas = (self._parcelas.valor() or "1").strip()
        return {
            "cliente_id": self._cliente.valor(),
            "vendedor_id": self._vendedor.valor(),
            "desconto": str(self._desconto.valor() or "0"),
            "forma_pagamento": self._forma.valor(),
            "parcelas": int(parcelas or "1"),
            "observacoes": (self._obs.valor() or None),
            "itens": self._itens.valor(),
        }

    def _salvar(self) -> None:
        """Venda é imutável: sempre POST (create), nunca PUT."""
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Validação", msg)
            campo.widget.setFocus()
            return
        self._btn_salvar.setEnabled(False)  # trava contra duplo POST
        payload = self._payload()
        rodar(
            lambda: self._api.criar(self.ENTIDADE, payload),
            on_ok=self._salvo,
            on_erro=lambda msg: self._erro_salvar(msg),
        )

    # ------------------------------------------------------------- ações

    def _acao_extra(self):
        cancelar, self._btn_cancelar_venda = botao_com_atalho("Cancelar Venda", "F8")
        self._btn_cancelar_venda.clicked.connect(self._cancelar_venda)
        return [cancelar]

    def _cancelar_venda(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(self, "Venda Balcão", "Selecione uma venda na lista.")
            return
        resposta = QMessageBox.question(
            self,
            "Cancelar venda",
            f"Cancelar a venda Nº {dado.get('numero')}?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return
        item_id = dado["id"]
        rodar(
            lambda: self._api.excluir(self.ENTIDADE, item_id),
            on_ok=lambda _out: self.recarregar(self._busca.texto()),
            on_erro=lambda msg: self._erro_salvar(msg),
        )