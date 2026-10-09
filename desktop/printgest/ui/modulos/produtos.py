"""Módulo Cadastro de Produtos & Serviços (mockup 2.2) sobre a base `PaginaCrud`.

Grid com marca/código/EAN-13, item, tipo, categoria e preço de venda (o mockup
mostra também saldo/margem — ficam para a etapa de Estoque). O formulário traz
identificação, precificação e controle de estoque. Fotos ficam como backlog.
"""

from __future__ import annotations

from printgest.core import catalogos
from printgest.core.api import Api
from printgest.ui.formulario import (
    CampoArea,
    CampoCheck,
    CampoCombo,
    CampoTexto,
    CampoValor,
    formatar_moeda,
    limpo,
    numero,
)
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
    LUGAR_BUSCA = "Buscar por código, código de barras/EAN-13 ou descrição..."
    CAMPO_NOME = "nome"

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._nomes_cat: dict[int, str] = {}
        self._carregar_categorias()

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._codigo = CampoTexto("Código Interno", mono=True, maximo=30).obrigatorio()
        self._barras = CampoTexto("Código de Barras / EAN-13", mono=True, maximo=30)
        self._nome = CampoTexto("Descrição do Item", maximo=160).obrigatorio()
        self._descricao = CampoArea("Descrição Técnica", linhas=2)
        self._tipo = CampoCombo("Tipo", _TIPOS, padrao="produto")
        self._unidade = CampoTexto("Unidade de Medida", maximo=12, valor="un")
        self._categoria = CampoCombo(
            "Categoria", [], padrao=None
        )

        self._preco_custo = CampoValor("Preço de Custo")
        self._preco_venda = CampoValor("Preço de Venda")

        self._controla = CampoCheck("Controla estoque")
        self._estoque_min = CampoValor("Estoque Mínimo")
        self._dimensoes = CampoTexto("Dimensões (L×A×E)", maximo=40)
        self._bloqueado = CampoCheck("Bloquear reajuste")

        return [
            (
                "Identificação",
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
            (
                "Precificação",
                [self._preco_custo, self._preco_venda],
            ),
            (
                "Estoque & Controle",
                [
                    self._controla,
                    self._estoque_min,
                    self._dimensoes,
                    self._bloqueado,
                ],
            ),
        ]

    def _padroes_do_form(self) -> None:
        self._tipo.definir("produto")
        self._unidade.definir("un")
        self._controla.definir(True)

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
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
        self._preco_custo.definir(dado.get("preco_custo"))
        self._preco_venda.definir(dado.get("preco_venda"))
        self._controla.definir(dado.get("controla_estoque"))
        self._estoque_min.definir(dado.get("estoque_minimo"))
        self._dimensoes.definir(dado.get("dimensoes"))
        self._bloqueado.definir(dado.get("bloqueado_reajuste"))

    # ------------------------------------------------------------ categorias

    def _carregar_categorias(self) -> None:
        catalogos.carregar(
            "categorias",
            lambda: self._api.listar("categorias", limit=1000),
            on_ok=self._categorias_recebidas,
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
        return {
            "codigo": self._codigo.valor(),
            "codigo_barras": limpo(self._barras.valor()),
            "nome": self._nome.valor(),
            "descricao": limpo(self._descricao.valor()),
            "tipo": self._tipo.valor(),
            "unidade": self._unidade.valor() or "un",
            "categoria_id": self._categoria.valor(),
            "preco_custo": numero(self._preco_custo),
            "preco_venda": numero(self._preco_venda),
            "controla_estoque": self._controla.valor(),
            "estoque_minimo": numero(self._estoque_min),
            "dimensoes": limpo(self._dimensoes.valor()),
            "bloqueado_reajuste": self._bloqueado.valor(),
        }