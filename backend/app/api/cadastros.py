"""Routers CRUD de cadastros — construídos pela fábrica para consistência.

Níveis de acesso (PRD v2.0 §5):
  - Cadastros: OPERADOR+ (operador tem "cadastros e movimento")
  - Usuários/Sistema: ADMIN (configurações de sistema)
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.crud_factory import criar_router_crud
from app.deps import DbDep, FilialDep, require_nivel
from app.models.cadastros import (
    Cliente,
    Fornecedor,
    Funcionario,
    Produto,
    ProdutoCategoria,
)
from app.models.enums import NivelAcesso
from app.schemas import ItemResponse
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
from app.services.crud import listar
from app.services.funcionario_service import criar_com_usuario

# Sem prefixo de grupo: as rotas são `/v1/clientes`, `/v1/produtos`,
# `/v1/funcionarios`... — é o contrato consumido pelo desktop
# (`/v1/{entidade}`), pela matriz de módulos (`gating._ROTAS_MODULOS`) e pela
# suíte. Um prefixo `/cadastros` aqui quebraria todos esses consumidores.
router = APIRouter(
    tags=["cadastros"],
    dependencies=[Depends(require_nivel(NivelAcesso.OPERADOR))],
)


# Clientes via factory
clientes_router = criar_router_crud(
    prefix="/clientes",
    model=Cliente,
    schema_in=ClienteCreate,
    schema_update=ClienteUpdate,
    schema_out=ClienteOut,
    campos_busca=["nome_razao", "cpf_cnpj", "email", "telefone", "celular"],
    campos_filtro=["tipo_pessoa"],
    tags=["cadastros"],
)
router.include_router(clientes_router)


# Fornecedores via factory
fornecedores_router = criar_router_crud(
    prefix="/fornecedores",
    model=Fornecedor,
    schema_in=FornecedorCreate,
    schema_update=FornecedorUpdate,
    schema_out=FornecedorOut,
    campos_busca=["nome_razao", "cpf_cnpj", "email", "telefone", "celular"],
    tags=["cadastros"],
)
router.include_router(fornecedores_router)


# ----------------------------------------------------------- funcionários (com login)
# M3 (§3.10): cadastro de funcionário cria usuário com primeiro acesso


@router.get("/funcionarios")
def listar_funcionarios(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    items, total = listar(
        db, Funcionario, filial_id=filial, q=q, limit=limit, offset=offset
    )
    return {
        "data": [FuncionarioOut.model_validate(f) for f in items],
        "meta": {"total": total, "limit": limit, "offset": offset},
    }


@router.post("/funcionarios")
def criar_funcionario(
    body: FuncionarioCreate,
    db: DbDep,
    filial: FilialDep,
) -> ItemResponse[FuncionarioOut]:
    """Cria funcionário com usuário de login (M3 §3.10 - primeiro acesso)."""
    dados = body.model_dump()
    dados["filial_id"] = filial
    funcionario = criar_com_usuario(db, Funcionario, dados)
    return ItemResponse(data=FuncionarioOut.model_validate(funcionario))


@router.put("/funcionarios/{item_id}")
def atualizar_funcionario(
    item_id: int,
    body: FuncionarioUpdate,
    db: DbDep,
    filial: FilialDep,
) -> ItemResponse[FuncionarioOut]:
    dados = body.model_dump(exclude_unset=True)
    # `login` é imutável e não é coluna de `funcionario` (vive em `usuario`);
    # ignorar aqui evita `setattr` na property somente-leitura.
    dados.pop("login", None)
    if dados:
        item = (
            db.query(Funcionario)
            .filter(
                Funcionario.id == item_id,
                Funcionario.filial_id == filial,
                Funcionario.ativo.is_(True),
            )
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Funcionário não encontrado.")
        for campo, valor in dados.items():
            setattr(item, campo, valor)
        db.commit()
        db.refresh(item)
    return ItemResponse(data=FuncionarioOut.model_validate(item))


@router.delete("/funcionarios/{item_id}", status_code=204)
def deletar_funcionario(
    item_id: int,
    db: DbDep,
    filial: FilialDep,
) -> None:
    item = (
        db.query(Funcionario)
        .filter(Funcionario.id == item_id, Funcionario.filial_id == filial)
        .first()
    )
    if item:
        item.ativo = False
        db.commit()


# Categorias via factory
categorias_router = criar_router_crud(
    prefix="/categorias",
    model=ProdutoCategoria,
    schema_in=CategoriaCreate,
    schema_update=CategoriaUpdate,
    schema_out=CategoriaOut,
    campos_busca=["nome"],
    tags=["cadastros"],
)
router.include_router(categorias_router)


# Produtos via factory
produtos_router = criar_router_crud(
    prefix="/produtos",
    model=Produto,
    schema_in=ProdutoCreate,
    schema_update=ProdutoUpdate,
    schema_out=ProdutoOut,
    campos_busca=["codigo", "codigo_barras", "nome"],
    tags=["cadastros"],
    nivel_acesso=NivelAcesso.OPERADOR,
)
router.include_router(produtos_router)


def registrar(api: APIRouter) -> None:
    api.include_router(router)
