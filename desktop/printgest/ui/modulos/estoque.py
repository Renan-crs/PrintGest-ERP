"""Módulo Estoque — consulta de saldos (4.1), movimentação manual/kardex (4.2) e reposição (4.3).

As três telas vivem na rota `/v1/estoque`:
  - Consulta: `GET /v1/estoque` + KPIs em `GET /v1/estoque/resumo`.
  - Movimentação: `POST /v1/estoque/movimentar` grava o kardex (origem
    `ajuste_manual`); `GET /v1/estoque/{produto_id}/kardex` abre a ficha.
  - Reposição: `GET /v1/estoque/reposicao` (saldo × mínimo, giro, sugestão).

Consulta e reposição são informativas: abrem a página em modo leitura, mantendo
apenas as ações de apoio (Kardex / Emitir Pedido) habilitadas.
"""

from __future__ import annotations

from decimal import Decimal

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import printgest.core.tarefas as tarefas
from printgest.ui import animacao
from printgest.ui.formulario import (
    CampoArea,
    CampoCombo,
    CampoTexto,
    CampoValor,
    em_volta,
    formatar_moeda,
    limpo,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.paginador import LOTE
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import (
    badge,
    botao_com_atalho,
    ElideLabel,
    estado_primario,
    estado_secundario,
)

_STATUS = {
    "critico": "CRÍTICO (repor)",
    "atencao": "ATENÇÃO",
    "normal": "NORMAL",
}

_ORIGENS = {
    "venda_balcao": "Venda Balcão",
    "ordem_servico": "O.S.",
    "pedido_compra": "Pedido Compra",
    "ajuste_manual": "Ajuste Manual",
}

_KARDEX_CHAVES = [
    "criado_em",
    "tipo",
    "origem",
    "documento_id",
    "operador_nome",
    "quantidade",
    "saldo_posterior",
    "motivo",
]
_KARDEX_COLUNAS = [
    "Data/Hora",
    "Tipo",
    "Origem",
    "Doc.",
    "Operador",
    "Qtd (±)",
    "Saldo",
    "Motivo / Obs.",
]


def _dt(valor) -> str:
    if not valor:
        return ""
    texto = str(valor)[:19].replace("T", " ")
    partes = texto.split(" ")
    if len(partes) != 2:
        return texto
    datas, horario = partes
    d = datas.split("-")
    return f"{d[2]}/{d[1]}/{d[0]} {horario}" if len(d) == 3 else texto


class PaginaEstoqueBase(PaginaCrud):
    """Consulta de saldos usada pelas telas 4.1 (gestão) e 4.2 (movimento)."""

    ENTIDADE = "estoque"
    ROTULO_PAGINA = "Gestão de Estoque & Bobinas"
    ROTULO_NOVO = "Novo lançamento"
    ROTULO_EXPORTAR = "Exportar CSV"
    GRUPO_LISTA = "INSUMOS CONTROLADOS"
    CHAVES = [
        "codigo",
        "nome",
        "categoria_nome",
        "saldo",
        "status",
        "preco_custo",
        "valor_estoque",
    ]
    COLUNAS = [
        "Cód",
        "Insumo & Especificação",
        "Categoria",
        "Saldo",
        "Status",
        "Custo Médio",
        "Valor Total",
    ]
    FILTROS = [
        ("", "Todos"),
        ("abaixo", "Abaixo do Mínimo"),
    ]

    def __init__(self, api, modo_leitura: bool = False) -> None:
        self._produto_atual: dict | None = None
        super().__init__(api, modo_leitura)

    # ------------------------------------------------------------ carregar

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        return self._api.consulta_estoque(
            q=q, abaixo_minimo=self._filtro == "abaixo", limit=LOTE, offset=offset
        )

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave in ("preco_custo", "valor_estoque"):
            return formatar_moeda(dado.get(chave))
        if chave == "status":
            return _STATUS.get(dado.get(chave), str(dado.get(chave) or ""))
        return super()._formatar_texto(dado, chave)

    # ------------------------------------------------------------ seleção

    def _carregar_no_form(self, dado: dict) -> None:
        self._produto_atual = dado
        codigo = str(dado.get("codigo") or "")
        titulo = f"Insumo: {self._rotulo_registro(dado)}"
        if codigo:
            titulo = f"{titulo} · {codigo}"
        self._form_titulo.setText(titulo)
        self._preencher_campos(dado)

    def _aplicar_modo_leitura_acoes(self) -> None:
        # Estoque é informativo: mesmo em modo leitura, as ações de apoio
        # (Ficha Kardex, Emitir Pedido) permanecem habilitadas.
        super()._aplicar_modo_leitura_acoes()
        for extra in getattr(self, "_acoes_extra", []):
            extra.setEnabled(True)
            for botao in extra.findChildren(QPushButton):
                botao.setEnabled(True)

    # ---------------------------------------------------------------- kardex

    def _acao_extra(self):
        kardex, self._btn_kardex = botao_com_atalho("Extrato Kardex", "F4")
        self._btn_kardex.clicked.connect(lambda: self._abrir_kardex(
            self._produto_atual or self._tabela.objeto_selecionado()
        ))
        return [kardex]

    def _abrir_kardex(self, dado: dict | None) -> None:
        if not dado:
            QMessageBox.information(
                self, "Kardex", "Selecione um insumo na lista."
            )
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(
            f"Ficha Kardex — {dado.get('codigo')} {dado.get('nome')}"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        tabela = TabelaDensa(_KARDEX_CHAVES, _KARDEX_COLUNAS)
        tabela.formata = self._formatar_kardex
        layout.addWidget(tabela, 1)
        fechar, _botao_fechar = botao_com_atalho("Fechar", "Esc")
        _botao_fechar.clicked.connect(dialog.close)
        rodape = QHBoxLayout()
        rodape.addStretch(1)
        rodape.addWidget(fechar)
        layout.addLayout(rodape)
        dialog.resize(820, 420)
        self._ultimo_dialogo_kardex = dialog
        self._kardex_tabela = tabela
        tarefas.rodar(
            lambda: self._api.kardex_estoque(dado["produto_id"], limit=200),
            on_ok=lambda saida: self._kardex_recebidos(saida, tabela),
            on_erro=lambda msg: QMessageBox.warning(dialog, "Kardex", msg),
        )
        animacao.revelar_janela(dialog)
        dialog.show()

    def _kardex_recebidos(self, saida: dict, tabela: TabelaDensa) -> None:
        tabela.preencher(saida.get("data", []))

    def _formatar_kardex(self, dado: dict, chave: str) -> str:
        if chave == "criado_em":
            return _dt(dado.get(chave))
        if chave == "tipo":
            return str(dado.get(chave, "")).upper()
        if chave == "origem":
            return _ORIGENS.get(dado.get(chave), str(dado.get(chave, "")).upper())
        if chave == "quantidade":
            valor = dado.get(chave)
            return "" if valor is None else str(valor)
        if chave == "saldo_posterior":
            valor = dado.get(chave)
            return "" if valor is None else str(valor)
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)


class PaginaEstoqueConsulta(PaginaEstoqueBase):
    """4.1 — Gestão de Estoque & Bobinas: consulta com KPIs na barra de título."""

    def __init__(self, api, modo_leitura: bool = False) -> None:
        self._ultimo_resumo: tuple | None = None
        super().__init__(api, modo_leitura=True)

    # --------------------------------------------------------------- KPIs

    def _badges_barra(self) -> list:
        self._badges_kpi = {
            "itens": badge("Itens: –", "primary"),
            "valor": badge("Avaliação: –", "primary"),
            "bobinas": badge("Bobinas: –", "atencao"),
            "abaixo": badge("Abaixo mín.: –", "erro"),
        }
        return [
            self._badges_kpi["itens"],
            self._badges_kpi["valor"],
            self._badges_kpi["bobinas"],
            self._badges_kpi["abaixo"],
        ]

    def _carregar_resumo(self, q: str, baixo: bool) -> None:
        def _aplicar(dados) -> None:
            if not isinstance(dados, dict):
                return
            self._badges_kpi["itens"].setText(f"Itens: {dados.get('total_itens', 0)}")
            self._badges_kpi["valor"].setText(
                f"Avaliação: {formatar_moeda(dados.get('valor_total'))}"
            )
            self._badges_kpi["bobinas"].setText(
                f"Bobinas: {dados.get('total_bobinas', 0)}"
            )
            self._badges_kpi["abaixo"].setText(
                f"Abaixo mín.: {dados.get('abaixo_minimo', 0)}"
            )

        def _erro(msg: str, status: int | None = None) -> None:
            # Antes o erro era engolido e os KPIs ficavam em "—" sem explicação.
            for badge_kpi in self._badges_kpi.values():
                badge_kpi.setText("—")
            if status not in (401, 423):
                QMessageBox.warning(self, "Resumo de estoque", msg)

        tarefas.rodar(
            lambda: self._api.resumo_estoque(q=q, abaixo_minimo=baixo),
            on_ok=_aplicar,
            on_erro=_erro,
        )

    def recarregar(self, q: str = "", offset: int | None = None) -> None:
        if offset is None:
            offset = self._offset
        baixo = self._filtro == "abaixo"
        super().recarregar(q, offset)
        # KPIs não mudam ao só paginar — refaz o resumo apenas quando a busca
        # ou o filtro mudam de fato (evita GET /resumo redundante por página).
        chave = (q, baixo)
        if chave != self._ultimo_resumo:
            self._ultimo_resumo = chave
            self._carregar_resumo(q, baixo)

    # ------------------------------------------------------------- formulário

    def _secoes(self):
        self._f_codigo = CampoTexto("Cód / SKU", mono=True)
        self._f_nome = CampoTexto("Insumo & Especificação")
        self._f_categoria = CampoTexto("Categoria")
        self._f_dimensoes = CampoTexto("Dimensões (bobina)")
        self._f_minimo = CampoValor("Estoque Mínimo", prefixo="")
        self._f_saldo = CampoValor("Saldo Atual", prefixo="")
        self._f_reservado = CampoValor("Reservado", prefixo="")
        self._f_disponivel = CampoValor("Disponível", prefixo="")
        self._f_custo = CampoValor("Custo Médio")
        self._f_venda = CampoValor("Preço de Venda")
        self._f_status = CampoTexto("Status")
        return [
            (
                "Identificação",
                [self._f_codigo, self._f_nome, self._f_categoria, self._f_dimensoes],
            ),
            (
                "Saldo & Valoração",
                [self._f_minimo, self._f_saldo, self._f_reservado, self._f_disponivel],
            ),
            ("Valores", [self._f_custo, self._f_venda, self._f_status]),
        ]

    def _preencher_campos(self, dado: dict) -> None:
        self._f_codigo.definir(dado.get("codigo"))
        self._f_nome.definir(dado.get("nome"))
        self._f_categoria.definir(dado.get("categoria_nome") or "—")
        self._f_dimensoes.definir(dado.get("dimensoes"))
        self._f_minimo.definir(dado.get("estoque_minimo"))
        self._f_saldo.definir(dado.get("saldo"))
        self._f_reservado.definir(dado.get("reservado"))
        self._f_disponivel.definir(dado.get("disponivel"))
        self._f_custo.definir(dado.get("preco_custo"))
        self._f_venda.definir(dado.get("preco_venda"))
        self._f_status.definir(_STATUS.get(dado.get("status"), dado.get("status") or ""))

class PaginaEstoqueMovimento(PaginaEstoqueBase):
    """4.2 — Movimentação Manual de Estoque & Ficha Kardex."""

    ROTULO_PAGINA = "Movimentação Manual de Estoque & Ficha Kardex"
    ROTULO_NOVO = "Movimentar Estoque"
    GRUPO_LISTA = "MOVIMENTAR INSUMO"

    def __init__(self, api, modo_leitura: bool = False) -> None:
        self._ultima_movimentacao: dict | None = None
        super().__init__(api, modo_leitura)

    def _secoes(self):
        self._f_codigo = CampoTexto("Insumo Selecionado", mono=True)
        self._tipo = CampoCombo(
            "Tipo de Movimentação",
            [
                ("entrada", "Entrada Avulsa / NF"),
                ("saida", "Perda Técnica de Máquina"),
                ("ajuste", "Ajuste Balanço / Inventário"),
            ],
        )
        self._quantidade = CampoValor("Qtd a Lançar", prefixo="")
        self._f_saldo = CampoTexto("Saldo Atual → Projetado", mono=True)
        self._f_minimo = CampoValor("Estoque Mínimo", prefixo="")
        self._motivo = CampoArea("Motivo / Justificativa Técnica", linhas=3)
        self._motivo.largo = True
        return [
            ("Lançamento Direto", [self._f_codigo]),
            ("Movimento", [self._tipo, self._quantidade, self._f_saldo]),
            ("Informação do Insumo", [self._f_minimo]),
            ("Complementos", [self._motivo]),
        ]

    def _conectar_campos(self) -> None:
        self._quantidade.edicao.textChanged.connect(
            lambda _t: self._atualizar_saldo_projetado()
        )
        self._tipo.widget.currentIndexChanged.connect(
            lambda _i: self._atualizar_saldo_projetado()
        )

    def _atualizar_saldo_projetado(self) -> None:
        atual = self._produto_atual
        if not atual:
            return
        saldo = Decimal(str(atual.get("saldo") or 0))
        qtd = self._quantidade.valor() or Decimal("0")
        tipo = self._tipo.valor()
        if tipo == "entrada":
            projetado = saldo + qtd
        elif tipo == "saida":
            projetado = saldo - qtd
        else:
            projetado = qtd
        self._f_saldo.definir(f"{saldo} → {projetado}")

    def _preencher_campos(self, dado: dict) -> None:
        self._f_codigo.definir(f"{dado.get('codigo')} — {dado.get('nome')}")
        self._f_minimo.definir(dado.get("estoque_minimo"))
        self._quantidade.definir(None)
        self._motivo.definir(None)
        self._atualizar_saldo_projetado()

    def _padroes_do_form(self) -> None:
        self._tipo.definir("entrada")

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._produto_atual:
            return ("Selecione um insumo na lista.", self._tipo)
        if not self._tipo.valor():
            return ("Informe o tipo de movimentação.", self._tipo)
        qtd = self._quantidade.valor()
        if not qtd or qtd <= 0:
            return ("Informe uma quantidade maior que zero.", self._quantidade)
        if self._tipo.valor() == "ajuste" and not limpo(self._motivo.valor()):
            return (
                "Informe o motivo da contagem (perda, quebra, acerto, contagem).",
                self._motivo,
            )
        return None

    def _payload(self) -> dict:
        return {
            "produto_id": self._produto_atual["produto_id"],
            "tipo": self._tipo.valor(),
            "quantidade": str(self._quantidade.valor()),
            "motivo": limpo(self._motivo.valor()),
        }

    def _salvar(self) -> None:
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Validação", msg)
            campo.widget.setFocus()
            return
        self._btn_salvar.setEnabled(False)  # trava contra duplo POST
        tarefas.rodar(
            lambda: self._api.movimentar_estoque(self._payload()),
            on_ok=self._movimentado,
            on_erro=self._erro_movimentar,
        )

    def _erro_movimentar(self, msg: str, status: int | None = None) -> None:
        self._btn_salvar.setEnabled(True)
        if status in (401, 423):
            titulo = "Sessão encerrada" if status == 401 else "Modo leitura"
            QMessageBox.warning(self, titulo, msg)
        elif status == 409:
            # Saída sem saldo: o detail do servidor já traz o produto/saldo.
            QMessageBox.warning(self, "Estoque insuficiente", msg)
        else:
            QMessageBox.critical(self, "Não foi possível movimentar", msg)

    def _movimentado(self, saida: dict) -> None:
        self._ultima_movimentacao = saida
        self._btn_salvar.setEnabled(True)
        self.recarregar(self._busca.texto())


class PaginaEstoqueReposicao(PaginaEstoqueBase):
    """4.3 — Relatório de Reposição & Curva de Consumo (recomendações)."""

    ENTIDADE = "estoque/reposicao"
    ROTULO_PAGINA = "Relatório de Reposição & Giro de Insumos"
    ROTULO_NOVO = "Gerar Reposição"
    ROTULO_EXPORTAR = "Exportar Excel / PDF"
    GRUPO_LISTA = "RECOMENDAÇÕES ATIVAS"
    LUGAR_BUSCA = "Buscar por código ou descrição..."
    CAMPO_NOME = "nome"
    CHAVES = [
        "codigo",
        "nome",
        "categoria_nome",
        "saldo",
        "estoque_minimo",
        "giro_diario",
        "autonomia_dias",
        "sugestao",
        "custo_est",
    ]
    COLUNAS = [
        "Cód",
        "Insumo & Especificação",
        "Categoria",
        "Saldo",
        "Est. Mín.",
        "Giro/Dia",
        "Autonomia",
        "Sugestão (Lote)",
        "Custo Est.",
    ]
    FILTROS = [
        ("", "Abaixo do Mínimo"),
        ("tudo", "Todos"),
    ]

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura=True)

    def _badges_barra(self) -> list:
        self._badge_itens = badge("Itens: –", "erro")
        self._badge_valor = badge("Reposição (pág.): –", "primary")
        return [self._badge_itens, self._badge_valor]

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        return self._api.reposicao_estoque(
            q=q, apenas_abaixo=self._filtro != "tudo", limit=LOTE, offset=offset
        )

    def _recebidos(self, q: str, offset: int, saida: dict) -> None:
        super()._recebidos(q, offset, saida)
        if not hasattr(self, "_badge_itens"):
            return
        linhas = saida.get("data", [])
        self._badge_itens.setText(f"Itens: {saida.get('total', 0)}")
        total = sum(
            (Decimal(str(i.get("custo_est") or 0)) for i in linhas),
            Decimal("0"),
        )
        self._badge_valor.setText(f"Reposição (pág.): {formatar_moeda(total)}")

    def _secoes(self):
        self._f_codigo = CampoTexto("Cód / SKU", mono=True)
        self._f_nome = CampoTexto("Insumo & Especificação")
        self._f_categoria = CampoTexto("Categoria")
        self._f_saldo = CampoValor("Saldo Atual", prefixo="")
        self._f_minimo = CampoValor("Est. Mínimo", prefixo="")
        self._f_giro = CampoValor("Giro Diário", prefixo="")
        self._f_autonomia = CampoTexto("Autonomia Estimada")
        self._f_sugestao = CampoValor("Sugestão (Lote)", prefixo="")
        self._f_custo = CampoValor("Custo Est.")
        return [
            ("Insumo", [self._f_codigo, self._f_nome, self._f_categoria]),
            (
                "Demanda & Nível",
                [self._f_saldo, self._f_minimo, self._f_giro, self._f_autonomia],
            ),
            ("Recomendação", [self._f_sugestao, self._f_custo]),
        ]

    def _preencher_campos(self, dado: dict) -> None:
        self._f_codigo.definir(dado.get("codigo"))
        self._f_nome.definir(dado.get("nome"))
        self._f_categoria.definir(dado.get("categoria_nome") or "—")
        self._f_saldo.definir(dado.get("saldo"))
        self._f_minimo.definir(dado.get("estoque_minimo"))
        self._f_giro.definir(dado.get("giro_diario"))
        autonomia = dado.get("autonomia_dias")
        self._f_autonomia.definir(
            f"{autonomia} dias" if autonomia is not None else "—"
        )
        self._f_sugestao.definir(dado.get("sugestao"))
        self._f_custo.definir(dado.get("custo_est"))

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "custo_est":
            return formatar_moeda(dado.get(chave))
        if chave == "autonomia_dias":
            valor = dado.get(chave)
            return f"{valor} d" if valor is not None else "—"
        return super()._formatar_texto(dado, chave)

    def _acao_extra(self):
        pedir, self._btn_pedir = botao_com_atalho("Emitir Pedido", "F9")
        self._btn_pedir.clicked.connect(self._emitir_pedido)
        return [pedir]

    def _emitir_pedido(self) -> None:
        dado = self._produto_atual
        if not dado:
            QMessageBox.information(
                self, self.ROTULO_PAGINA, "Selecione um insumo na lista."
            )
            return
        QMessageBox.information(
            self,
            self.ROTULO_PAGINA,
            "Pedidos de Compra consolidados serão gerados na próxima etapa "
            f"(recomendação atual: {dado.get('sugestao')} unidades).",
        )


__all__ = [
    "PaginaEstoque",
    "PaginaEstoqueConsulta",
    "PaginaEstoqueMovimento",
    "PaginaEstoqueReposicao",
    "PaginaEstoqueBase",
]


# ================================================================ host Estoque


class PaginaEstoqueTransferencias(QWidget):
    """Transferência entre filiais em dois passos (PRD §5.6)."""

    # Colunas reais do `TransferenciaOut` — `produto_nome`/`destino` não
    # existem no contrato e deixavam a grade sempre com "—".
    CHAVES = ["numero", "produto_id", "quantidade", "estado", "filial_destino_id"]
    COLUNAS = ["Nº", "Produto ID", "Qtd", "Estado", "Destino ID"]
    PESOS = [3, 4, 2, 3, 4]
    _ESTADOS = {
        "enviada": "Enviada",
        "recebida": "Recebida",
        "cancelada": "Cancelada",
    }

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        titulo = ElideLabel("Transferências entre filiais")
        titulo.setObjectName("titulo")
        col.addWidget(titulo)
        aviso = QLabel(
            "Saída na origem; o destino só recebe o estoque após confirmar."
        )
        aviso.setObjectName("subtitulo")
        col.addWidget(aviso)

        self._tabela = TabelaDensa(self.CHAVES, self.COLUNAS, self.PESOS)
        self._tabela.formata = self._formatar
        col.addWidget(self._tabela, 1)

        formulario = QWidget()
        formulario.setObjectName("card")
        linha = QHBoxLayout(formulario)
        self._destino = CampoTexto("Filial destino (ID)", maximo=10)
        self._produto = CampoTexto("Produto (ID)", maximo=10)
        # CampoValor aceita o formato brasileiro ("2,5") que o Pydantic
        # rejeitaria se enviado como string.
        self._quantidade = CampoValor("Quantidade", prefixo="")
        linha.addWidget(em_volta(self._destino))
        linha.addWidget(em_volta(self._produto))
        linha.addWidget(em_volta(self._quantidade))
        self._btn_enviar = QPushButton("Enviar")
        estado_primario(self._btn_enviar)
        self._btn_enviar.clicked.connect(self._enviar)
        linha.addWidget(self._btn_enviar)
        col.addWidget(formulario)

        acoes = QHBoxLayout()
        self._btn_receber = QPushButton("Confirmar recebimento")
        estado_secundario(self._btn_receber)
        self._btn_receber.clicked.connect(self._receber)
        self._btn_cancelar = QPushButton("Cancelar envio")
        estado_secundario(self._btn_cancelar)
        self._btn_cancelar.clicked.connect(self._cancelar)
        acoes.addStretch(1)
        acoes.addWidget(self._btn_receber)
        acoes.addWidget(self._btn_cancelar)
        col.addLayout(acoes)
        self._carregar()

    def _formatar(self, dado: dict, chave: str) -> str:
        if chave == "estado":
            estado = str(dado.get("estado") or "")
            return self._ESTADOS.get(estado, estado or "—")
        valor = dado.get(chave)
        return str(valor) if valor is not None else "—"

    def _carregar(self) -> None:
        def ok(saida: dict) -> None:
            itens = saida.get("data", []) if isinstance(saida, dict) else []
            self._tabela.preencher(itens)

        tarefas.rodar(self._api.listar_transferencias, ok, self._erro)

    def _erro(self, msg: str, status: int | None = None) -> None:
        # `tarefas.rodar` só entrega o status a callbacks com 2 parâmetros.
        if status in (401, 423):
            titulo = "Sessão encerrada" if status == 401 else "Modo leitura"
            QMessageBox.warning(self, titulo, msg)
            return
        QMessageBox.warning(self, "Transferências", msg)

    def _selecionada(self) -> dict | None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(self, "Transferências", "Selecione uma transferência.")
        return dado

    def _validar(self):
        if not str(self._destino.valor() or "").strip().isdigit():
            return ("Informe o ID da filial destino.", self._destino)
        if not str(self._produto.valor() or "").strip().isdigit():
            return ("Informe o ID do produto.", self._produto)
        qtd = self._quantidade.valor()
        if qtd is None or qtd <= 0:
            return ("Informe uma quantidade maior que zero.", self._quantidade)
        return None

    def _enviar(self) -> None:
        if self._modo_leitura:
            return
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Transferência", msg)
            if getattr(campo, "widget", None) is not None:
                campo.widget.setFocus()
            return
        # Trava contra duplo clique (a API não é idempotente em POST).
        self._btn_enviar.setEnabled(False)
        payload = {
            "filial_destino_id": int(str(self._destino.valor()).strip()),
            "produto_id": int(str(self._produto.valor()).strip()),
            "quantidade": str(self._quantidade.valor()),
        }

        def _ok(_saida) -> None:
            self._btn_enviar.setEnabled(True)
            self._carregar()

        def _erro(msg: str, status: int | None = None) -> None:
            self._btn_enviar.setEnabled(True)
            self._erro(msg, status)

        tarefas.rodar(lambda: self._api.transferir(payload), _ok, _erro)

    def _receber(self) -> None:
        dado = self._selecionada()
        if dado is None or self._modo_leitura:
            return
        tarefas.rodar(
            lambda: self._api.receber_transferencia(dado["id"]),
            lambda _: self._carregar(),
            self._erro,
        )

    def _cancelar(self) -> None:
        dado = self._selecionada()
        if dado is None or self._modo_leitura:
            return
        tarefas.rodar(
            lambda: self._api.cancelar_transferencia(dado["id"]),
            lambda _: self._carregar(),
            self._erro,
        )


class PaginaEstoque(QWidget):
    """Menu "Estoque": hospeda as sub-abas (Consulta, Movimentação, Reposição)."""

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._abas = [
            ("Consulta", PaginaEstoqueConsulta),
            ("Movimentação", PaginaEstoqueMovimento),
            ("Reposição", PaginaEstoqueReposicao),
            ("Transferências", PaginaEstoqueTransferencias),
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
        self._trocar(0)

    def _barra(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 16, 20, 0)
        linha.setSpacing(8)
        titulo = ElideLabel("Estoque")
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
        pagina = classe(self._api, modo_leitura=self._modo_leitura)
        if self._atual is not None:
            self._atual.setVisible(False)
            self._corpo_layout.removeWidget(self._atual)
            self._atual.deleteLater()
        self._corpo_layout.addWidget(pagina)
        self._atual = pagina
        for i, botao in enumerate(self._botoes):
            botao.setChecked(i == indice)
