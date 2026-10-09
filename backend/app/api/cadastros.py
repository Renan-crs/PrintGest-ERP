"""Routers CRUD de cadastros — construídos pela fábrica para consistência.

Níveis de acesso (PRD v2.0 §5):
  - Cadastros: OPERADOR+ (operador tem "cadastros e movimento")
  - Usuários/Sistema: ADMIN (configurações de sistema)
"""

from fastapi import APIRouter

from app.api.crud_factory import criar_router_crud
from app.models.cadastros import (
    Cliente,
    Fornecedor,
    Funcionario,
    Produto,
    ProdutoCategoria,
)
from app.models.enums import NivelAcesso
from app.schemas.cadastros import (
    CategoriaCreate,
    CategoriaOut,
    CategoriaUpdate,
    ClienteCreate,
    ClienteOut,
    ClienteUpdate,
    FornecedorCreate,
    FornecedorOut,
    FornecedorUpdate,
    FuncionarioCreate,
    FuncionarioOut,
    FuncionarioUpdate,
    ProdutoCreate,
    ProdutoOut,
    ProdutoUpdate,
)

clientes = criar_router_crud(
    prefix="/clientes",
    model=Cliente,
    schema_in=ClienteCreate,
    schema_update=ClienteUpdate,
    schema_out=ClienteOut,
    campos_busca=["nome_razao", "cpf_cnpj", "email", "telefone", "celular"],
    campos_filtro=["tipo_pessoa"],
    tags=["cadastros"],
)

fornecedores = criar_router_crud(
    prefix="/fornecedores",
    model=Fornecedor,
    schema_in=FornecedorCreate,
    schema_update=FornecedorUpdate,
    schema_out=FornecedorOut,
    campos_busca=["nome_razao", "cpf_cnpj", "email", "telefone", "celular"],
    tags=["cadastros"],
)

funcionarios = criar_router_crud(
    prefix="/funcionarios",
    model=Funcionario,
    schema_in=FuncionarioCreate,
    schema_update=FuncionarioUpdate,
    schema_out=FuncionarioOut,
    campos_busca=["nome", "cpf", "cargo"],
    tags=["cadastros"],
)

categorias = criar_router_crud(
    prefix="/categorias",
    model=ProdutoCategoria,
    schema_in=CategoriaCreate,
    schema_update=CategoriaUpdate,
    schema_out=CategoriaOut,
    campos_busca=["nome"],
    tags=["cadastros"],
)

produtos = criar_router_crud(
    prefix="/produtos",
    model=Produto,
    schema_in=ProdutoCreate,
    schema_update=ProdutoUpdate,
    schema_out=ProdutoOut,
    campos_busca=["codigo", "codigo_barras", "nome"],
    tags=["cadastros"],
    nivel_acesso=NivelAcesso.OPERADOR,
)


def registrar(api: APIRouter) -> None:
    api.include_router(clientes)
    api.include_router(fornecedores)
    api.include_router(funcionarios)
    api.include_router(categorias)
    api.include_router(produtos)