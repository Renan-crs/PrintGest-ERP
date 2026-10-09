"""Módulo Cadastro de Categorias sobre a base `PaginaCrud`.

Lista simples + formulário de uma seção. Usada principalmente como origem do
combo de categorias da tela de produtos.
"""

from __future__ import annotations

from printgest.core.api import Api
from printgest.ui.formulario import CampoArea, CampoTexto, limpo
from printgest.ui.modulos.pagina_crud import PaginaCrud

ENTIDADE = "categorias"

CHAVES = ["id", "nome", "description"]
COLUNAS = ["Cód.", "Categoria", "Descrição"]


class PaginaCategorias(PaginaCrud):
    ENTIDADE = ENTIDADE
    ROTULO_PAGINA = "Cadastro de Categorias"
    ROTULO_NOVO = "Nova Categoria"
    GRUPO_LISTA = "CATEGORIAS DO CATÁLOGO"
    CHAVES = CHAVES
    COLUNAS = COLUNAS
    LUGAR_BUSCA = "Buscar por nome ou descrição..."
    CAMPO_NOME = "nome"

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._nome = CampoTexto("Nome da Categoria", maximo=80).obrigatorio()
        self._descricao = CampoArea("Descrição", linhas=3)
        return [("", [self._nome, self._descricao])]

    def _preencher_campos(self, dado: dict) -> None:
        self._nome.definir(dado.get("nome"))
        self._descricao.definir(dado.get("description"))

    def _validar(self):
        if not self._nome.valido():
            return ("Informe o nome da categoria.", self._nome)
        return None

    def _payload(self) -> dict:
        return {"nome": self._nome.valor(), "description": limpo(self._descricao.valor())}