"""Módulo Cadastro de Produtos & Serviços (mockup 2.2) sobre a base `PaginaCrud`.

Grid com marca/código/EAN-13, item, tipo, categoria e preço de venda (o mockup
mostra também saldo/margem — ficam para a etapa de Estoque). O formulário traz
identificação, precificação e controle de estoque. Fotos ficam como backlog.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QPushButton

import printgest.core.tarefas as tarefas
from printgest.core import catalogos
from printgest.core.api import Api
from printgest.core.notificacao import mensagem_segura, titulo_erro
from printgest.ui.formulario import (
    CampoArea,
    CampoArquivo,
    CampoCheck,
    CampoCombo,
    CampoTexto,
    CampoValor,
    formatar_moeda,
    limpo,
    numero,
)
from printgest.ui.modulos.dialogo_variacoes import DialogoVariacoes
from printgest.ui.paginador import LOTE
from printgest.ui.modulos.pagina_crud import PaginaCrud

ENTIDADE = "produtos"

CHAVES = ["id", "codigo", "nome", "tipo", "categoria_nome", "preco_venda"]
COLUNAS = ["Ref", "Código", "Item", "Tipo", "Categoria", "Preço Venda"]

_TIPOS = [("produto", "Produto"), ("servico", "Serviço")]


class PaginaProdutos(PaginaCrud):
    ENTIDADE = ENTIDADE
    ROTULO_PAGINA = "Cadastro de Produtos & Serviços"
    ROTULO_NOVO = "Novo Produto / Serviço"
    GRUPO_LISTA = "CATÁLOGO DE PRODUTOS E SERVIÇOS"
    CHAVES = CHAVES
    COLUNAS = COLUNAS
    # Ref precisa de largura para "#00004" (antes virava "#00…").
    PESOS = [2, 2, 5, 2, 3, 3]
    FILTROS = [
        ("", "Todos"), ("produto", "Produtos"),
        ("servico", "Serviços"), ("variante", "Variações"),
    ]
    CHAVE_FILTRO = "tipo"
    # Filtros enviados ao servidor — essencial para catálogos >50 itens.
    FILTRO_LOCAL = False
    LUGAR_BUSCA = "Buscar por código, código de barras/EAN-13 ou descrição..."
    CAMPO_NOME = "nome"
    VAZIO = "Nenhum produto ou serviço encontrado. Clique em Novo Produto / Serviço (F6)."
    TIPO_FIXO = ""

    def __init__(
        self, api: Api, modo_leitura: bool = False, nivel: str | None = None
    ) -> None:
        # Antes do super(): `recarregar()` do `PaginaCrud` formata a coluna
        # `categoria_nome` já durante a construção (em testes o `rodar` roda de
        # forma síncrona), então o cache precisa existir antes.
        self._nomes_cat: dict[int, str] = {}
        super().__init__(api, modo_leitura)
        # `_padroes_do_form()` roda antes do botão existir; aplica o estado agora.
        self._atualizar_botao_variacoes()
        if nivel == "operador":
            # RBAC: operador consulta o catálogo, mas não altera preços.
            self._preco_custo.habilitar(False)
            self._preco_venda.habilitar(False)
        self._carregar_categorias()

    def _acao_extra(self) -> list:
        """Gera variantes (matriz de produtos) a partir de um produto pai."""
        botao = QPushButton("Gerar variações")
        botao.setObjectName("acaoLinha")
        botao.setToolTip(
            "Cria variantes com SKU único e estoque próprio a partir de "
            "combinações de tamanho, marca e cor. Combinações repetidas ou já "
            "existentes são ignoradas."
        )
        botao.clicked.connect(self._gerar_variacoes)
        self._btn_variacoes = botao

        propagar = QPushButton("Propagar preço")
        propagar.setObjectName("acaoLinha")
        propagar.setToolTip(
            "Atualiza preço, custo e mínimo das variantes com os valores do "
            "produto pai (GERENTE+)"
        )
        propagar.clicked.connect(self._propagar_preco)
        self._btn_propagar = propagar
        return [botao, propagar]

    @staticmethod
    def _dominios_variacoes(produtos: list[dict]) -> dict[str, list[str]]:
        """Valores já usados no catálogo para sugerir domínios consistentes."""
        encontrado: dict[str, set[str]] = {
            "tamanho": set(), "marca": set(), "cor": set()
        }
        for produto in produtos:
            for chave in encontrado:
                valor = str(produto.get(f"atrib_{chave}") or "").strip()
                if valor:
                    encontrado[chave].add(valor)
        return {chave: sorted(valores)[:12] for chave, valores in encontrado.items()}

    def _gerar_variacoes(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado or self._editando_id is None:
            QMessageBox.information(
                self, "Variações", "Selecione o produto pai na lista."
            )
            return
        if getattr(self, "_modo_leitura", False):
            return

        def _abrir(saida) -> None:
            produtos = saida.get("data", []) if isinstance(saida, dict) else []
            self._dialogo_variacoes(dado, self._dominios_variacoes(produtos))

        # Carrega o catálogo para sugerir os domínios (P/M/G, marca, cor).
        tarefas.rodar(
            lambda: self._api.listar("produtos", limit=200),
            _abrir,
            lambda msg, status=None: self._dialogo_variacoes(dado, {}),
        )

    def _dialogo_variacoes(self, dado: dict, dominios: dict[str, list[str]]) -> None:
        dialogo = DialogoVariacoes(
            produto_pai=dado, dominios=dominios, parent=self
        )
        if dialogo.exec() != dialogo.DialogCode.Accepted:
            return
        variacoes = dialogo.valor()
        if not variacoes:
            return
        confirma = QMessageBox.question(
            self,
            "Gerar variações",
            f"{len(variacoes)} variante(s) serão processadas.\n"
            "Combinações já existentes são ignoradas (idempotente). Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirma != QMessageBox.StandardButton.Yes:
            return

        botao = getattr(self, "_btn_variacoes", None)
        if botao is not None:
            botao.setEnabled(False)

        def feito(resp) -> None:
            if botao is not None:
                botao.setEnabled(True)
            catalogos.invalidar("produtos")
            self.recarregar(self._busca.texto())
            criados = resp if isinstance(resp, list) else resp.get("data", [])
            QMessageBox.information(
                self, "Variações", f"{len(criados)} variante(s) criada(s)."
            )

        def erro(msg: str, status: int | None = None) -> None:
            if botao is not None:
                botao.setEnabled(True)
            titulo = titulo_erro(status, msg, "Variações")
            if titulo == "Variações":
                titulo = (
                    "Sem permissão" if status == 403
                    else "Conflito de SKU" if status == 409
                    else titulo
                )
            orientacao = (
                "\n\nRevise os códigos de barras/SKU e tente novamente."
                if status == 409 else ""
            )
            QMessageBox.warning(
                self, titulo, f"{mensagem_segura(msg)}{orientacao}"
            )

        tarefas.rodar(
            lambda: self._api.gerar_variacoes(
                {
                    "produto_pai_id": dado["id"],
                    "prefixo_sku": dado.get("codigo", ""),
                    "variacoes": variacoes,
                }
            ),
            feito,
            erro,
        )

    def _propagar_preco(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado or self._editando_id is None:
            QMessageBox.information(
                self, "Variações", "Selecione o produto pai na lista."
            )
            return
        confirma = QMessageBox.question(
            self,
            "Propagar preço",
            "Atualizar preço, custo e estoque mínimo das variantes com os "
            "valores deste produto?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirma != QMessageBox.StandardButton.Yes:
            return

        self._btn_propagar.setEnabled(False)

        def ok(resp) -> None:
            self._btn_propagar.setEnabled(True)
            catalogos.invalidar("produtos")
            self.recarregar(self._busca.texto())
            total = (resp or {}).get("variantes_atualizadas", 0)
            QMessageBox.information(
                self, "Propagar preço", f"{total} variante(s) atualizada(s)."
            )

        def erro(msg: str, status: int | None = None) -> None:
            self._btn_propagar.setEnabled(True)
            titulo = titulo_erro(status, msg, "Propagar preço")
            if titulo == "Propagar preço" and status == 403:
                titulo = "Sem permissão"
            QMessageBox.warning(self, titulo, mensagem_segura(msg))

        tarefas.rodar(
            lambda: self._api.propagar_preco(dado["id"]), ok, erro
        )

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._codigo = CampoTexto("Código Interno", mono=True, maximo=30).obrigatorio()
        self._barras = CampoTexto("Código de Barras / EAN-13", mono=True, maximo=30)
        self._nome = CampoTexto("Descrição do Item", maximo=160).obrigatorio().larga()
        self._descricao = CampoArea("Descrição Técnica", linhas=2).larga()
        self._tipo = CampoCombo("Tipo", _TIPOS, padrao="produto")
        self._unidade = CampoTexto("Unidade de Medida", maximo=12, valor="un")
        self._categoria = CampoCombo("Categoria", [], padrao=None)

        # Metadados da variante (somente-leitura) + atributos editáveis.
        self._pai_id = CampoTexto("Produto pai (ID)", mono=True)
        self._sku = CampoTexto("SKU", mono=True)
        self._uuid = CampoTexto("UUID", mono=True)
        self._atrib_tamanho = CampoTexto("Tamanho", maximo=40)
        self._atrib_marca = CampoTexto("Marca", maximo=60)
        self._atrib_cor = CampoTexto("Cor", maximo=60)

        self._preco_custo = CampoValor("Preço de Custo")
        self._preco_venda = CampoValor("Preço de Venda")

        self._controla = CampoCheck("Controla estoque")
        self._estoque_min = CampoValor("Estoque Mínimo", prefixo="")
        self._dimensoes = CampoTexto("Dimensões (L×A×E)", maximo=40)
        self._bloqueado = CampoCheck("Bloquear reajuste")
        self._foto1 = CampoArquivo("Foto 1").larga()
        self._foto2 = CampoArquivo("Foto 2").larga()

        return [
            (
                "Cadastro",
                [
                    self._codigo,
                    self._barras,
                    self._nome,
                    self._descricao,
                    self._tipo,
                    self._unidade,
                    self._categoria,
                ],
            ),
            # Preço e estoque antes das fotos: em 768px ficavam abaixo da
            # dobra e o operador precisava rolar para conferir/alterar.
            (
                "Precificação",
                [self._preco_custo, self._preco_venda],
            ),
            (
                "Estoque",
                [
                    self._controla,
                    self._estoque_min,
                    self._dimensoes,
                    self._bloqueado,
                ],
            ),
            (
                "Variação (filha)",
                [
                    self._pai_id, self._sku, self._uuid,
                    self._atrib_tamanho, self._atrib_marca, self._atrib_cor,
                ],
            ),
            ("Imagens", [self._foto1, self._foto2]),
        ]

    def _conectar_campos(self) -> None:
        self._tipo.widget.currentIndexChanged.connect(self._tipo_mudou)
        if self.TIPO_FIXO:
            self._tipo.visivel(False)
        self._tipo_mudou()

    def _tipo_mudou(self) -> None:
        produto = self._tipo_atual() == "produto"
        for campo in (self._controla, self._estoque_min, self._dimensoes, self._bloqueado):
            campo.visivel(produto)
        if not produto:
            self._controla.definir(False)

    def _tipo_atual(self) -> str:
        return self.TIPO_FIXO or self._tipo.valor() or "produto"

    def _padroes_do_form(self) -> None:
        self._tipo.definir(self.TIPO_FIXO or "produto")
        self._unidade.definir("un")
        self._controla.definir(self.TIPO_FIXO != "servico")
        self._tipo_mudou()
        for campo in (self._pai_id, self._sku, self._uuid):
            campo.definir(None)
            campo.habilitar(False)
        for campo in (self._atrib_tamanho, self._atrib_marca, self._atrib_cor):
            campo.definir(None)
            campo.habilitar(False)
        self._atualizar_botao_variacoes()

    def _selecao_mudou(self) -> None:
        super()._selecao_mudou()
        self._atualizar_botao_variacoes()

    def _atualizar_botao_variacoes(self) -> None:
        """Só faz sentido gerar variações de um produto já salvo e selecionado."""
        botao = getattr(self, "_btn_variacoes", None)
        if botao is None:
            return
        habilitado = self._editando_id is not None and not self._modo_leitura
        botao.setEnabled(habilitado)
        propagar = getattr(self, "_btn_propagar", None)
        if propagar is not None:
            propagar.setEnabled(habilitado)

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "nome" and dado.get("produto_pai_id"):
            # Distingue a variante filha do produto pai na grade.
            return f"↳ {dado.get('nome') or ''}"
        if chave == "tipo":
            return str(dado.get("tipo", "")).upper()
        if chave == "categoria_nome":
            cat_id = dado.get("categoria_id")
            return self._nomes_cat.get(cat_id, "") if cat_id else ""
        if chave == "preco_venda":
            return formatar_moeda(dado.get("preco_venda"))
        return super()._formatar_texto(dado, chave)

    def _preencher_campos(self, dado: dict) -> None:
        self._codigo.definir(dado.get("codigo"))
        self._barras.definir(dado.get("codigo_barras"))
        self._nome.definir(dado.get("nome"))
        self._descricao.definir(dado.get("descricao"))
        self._tipo.definir(dado.get("tipo"))
        self._unidade.definir(dado.get("unidade") or "un")
        self._categoria.definir(dado.get("categoria_id"))

        pai_id = dado.get("produto_pai_id")
        self._pai_id.definir(f"#{pai_id}" if pai_id else None)
        self._pai_id.habilitar(False)
        self._sku.definir(dado.get("sku"))
        self._sku.habilitar(False)
        self._uuid.definir(dado.get("uuid"))
        self._uuid.habilitar(False)
        for campo, chave in (
            (self._atrib_tamanho, "atrib_tamanho"),
            (self._atrib_marca, "atrib_marca"),
            (self._atrib_cor, "atrib_cor"),
        ):
            campo.definir(dado.get(chave))
            campo.habilitar(pai_id is not None and not self._modo_leitura)

        self._preco_custo.definir(dado.get("preco_custo"))
        self._preco_venda.definir(dado.get("preco_venda"))
        self._controla.definir(dado.get("controla_estoque"))
        self._estoque_min.definir(dado.get("estoque_minimo"))
        self._dimensoes.definir(dado.get("dimensoes"))
        self._bloqueado.definir(dado.get("bloqueado_reajuste"))
        self._foto1.definir(dado.get("foto1_path"))
        self._foto2.definir(dado.get("foto2_path"))
        self._tipo_mudou()

    # ------------------------------------------------------------ categorias

    def _carregar_categorias(self) -> None:
        def erro(msg: str, status: int | None = None) -> None:
            # Sem modal: a consulta de categorias é auxiliar e não pode travar
            # a abertura da tela (nem o harness de layout).
            self._categoria.widget.setToolTip(
                f"Categorias indisponíveis ({status or 'erro'}): {msg}"
            )

        catalogos.carregar(
            "categorias",
            lambda: self._api.listar("categorias", limit=1000),
            on_ok=self._categorias_recebidas,
            on_erro=erro,
        )

    def _categorias_recebidas(self, saida: dict) -> None:
        dados = saida.get("data", [])
        self._nomes_cat = {r["id"]: r["nome"] for r in dados}
        self._categoria.alterar_opcoes([(r["id"], r["nome"]) for r in dados])

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._codigo.valido():
            return ("Informe o código interno.", self._codigo)
        if not self._nome.valido():
            return ("Informe a descrição do item.", self._nome)
        return None

    def _payload(self) -> dict:
        servico = self._tipo_atual() == "servico"
        dados = {
            "codigo": self._codigo.valor(),
            "codigo_barras": limpo(self._barras.valor()),
            "nome": self._nome.valor(),
            "descricao": limpo(self._descricao.valor()),
            "tipo": self._tipo_atual(),
            "unidade": self._unidade.valor() or "un",
            "categoria_id": self._categoria.valor(),
            "preco_custo": numero(self._preco_custo),
            "preco_venda": numero(self._preco_venda),
            "controla_estoque": False if servico else self._controla.valor(),
            "estoque_minimo": "0" if servico else numero(self._estoque_min),
            "dimensoes": limpo(self._dimensoes.valor()),
            "foto1_path": limpo(self._foto1.valor()),
            "foto2_path": limpo(self._foto2.valor()),
            "bloqueado_reajuste": self._bloqueado.valor(),
        }
        # Atributos só são enviados para uma filha (pai é imutável no backend).
        if self._pai_id.valor():
            dados.update({
                "atrib_tamanho": limpo(self._atrib_tamanho.valor()),
                "atrib_marca": limpo(self._atrib_marca.valor()),
                "atrib_cor": limpo(self._atrib_cor.valor()),
            })
        return dados

    # --------------------------------------------------------------- filtros

    def _listar(self, q: str, offset: int, filtros: dict) -> dict:
        parametros = dict(filtros)
        if self.TIPO_FIXO:
            parametros["tipo"] = self.TIPO_FIXO
        if self._filtro == "variante":
            parametros.pop("tipo", None)
            parametros["somente_variantes"] = True
        elif self._filtro in ("produto", "servico"):
            parametros["tipo"] = self._filtro
        return self._api.listar_com_filtros(
            self.ENTIDADE, q=q, limit=LOTE, offset=offset, **parametros
        )

    def _aplicar_filtro_local(self, linhas: list[dict]) -> list[dict]:
        # O filtro de variantes é server-side; aqui só o fixo da tela Serviços.
        if self.TIPO_FIXO:
            return [r for r in linhas if r.get("tipo") == self.TIPO_FIXO]
        return linhas


class PaginaServicos(PaginaProdutos):
    """Mesma tela de Produtos filtrada por `tipo=servico` (item de menu "Serviços")."""

    ROTULO_PAGINA = "Cadastro de Serviços"
    ROTULO_NOVO = "Novo Serviço"
    FILTROS: list[tuple[str, str]] = []
    FILTRO_LOCAL = True
    CHAVE_FILTRO = ""
    VAZIO = "Nenhum serviço encontrado. Clique em Novo Serviço (F6)."
    TIPO_FIXO = "servico"

    def _padroes_do_form(self) -> None:
        self._tipo.definir("servico")
        self._unidade.definir("un")
        self._controla.definir(False)
        self._tipo_mudou()

    def _acao_extra(self) -> list:
        # Serviço não tem variações com estoque — o backend também recusa.
        return []
