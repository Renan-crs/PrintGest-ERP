"""Leituras de catálogo usadas pelo PDV — acessíveis a CAIXA (RBAC §5).

Os routers de cadastro exigem OPERADOR para **escrita**, e o de usuários exige
ADMIN. O operador de caixa (nível CAIXA) precisa apenas **ler** clientes,
produtos, vendedores e operadores para montar a venda e o filtro do histórico —
sem poder alterá-los. Este router expõe somente GET, com o mesmo contrato
paginated dos cadastros (`ListaResponse`) e um teto alto o suficiente para
carregar o catálogo inteiro de uma vez (a fábrica genérica limita a 200, o que
deixava a grade do PDV incompleta em instalações com mais produtos).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import DbDep, FilialDep, require_nivel
from app.models.cadastros import Cliente, Funcionario, Produto
from app.models.core import Usuario
from app.models.enums import NivelAcesso
from app.schemas import ItemResponse, ListaResponse
from app.schemas.cadastros import ClienteOut, FuncionarioOut, ProdutoOut
from app.schemas.common import MetaPaginacao
from app.services import variacao_service
from app.services.crud import listar

router = APIRouter(
    prefix="/pdv",
    tags=["pdv"],
    # `require_nivel(CAIXA)` é hierárquico: CAIXA, OPERADOR, GERENTE e ADMIN
    # leem. Nenhuma rota aqui grava dados.
    dependencies=[Depends(require_nivel(NivelAcesso.CAIXA))],
)

# Teto do catálogo completo (a fábrica de CRUD usa 200 para listas de tela).
_LIMITE_CATALOGO = 5000


def _lista(
    db,
    filial: int,
    modelo,
    schema_out,
    campos_busca: list[str],
    q: str | None,
    limit: int,
    offset: int,
) -> ListaResponse:
    limite = min(max(limit, 1), _LIMITE_CATALOGO)
    desloc = max(offset, 0)
    itens, total = listar(
        db,
        modelo,
        filial_id=filial,
        q=q,
        campos_busca=campos_busca,
        limit=limite,
        offset=desloc,
    )
    return ListaResponse(
        data=[schema_out.model_validate(i) for i in itens],
        meta=MetaPaginacao(total=total, limit=limite, offset=desloc),
    )


# Rota específica ANTES da genérica (embora não haja detalhe aqui, a ordem
# evita ambiguidade caso uma seja adicionada depois).
@router.get("/produtos/buscar-sku/{termo}", response_model=ItemResponse[ProdutoOut])
def buscar_sku(termo: str, db: DbDep, filial: FilialDep):
    produto = variacao_service.buscar_por_sku(db, filial_id=filial, termo=termo)
    if produto is None:
        raise HTTPException(404, "Produto/variante não encontrado por SKU.")
    return ItemResponse(data=ProdutoOut.model_validate(produto))


@router.get("/produtos")
def produtos(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    limit: int = Query(default=_LIMITE_CATALOGO, ge=1, le=_LIMITE_CATALOGO),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse:
    return _lista(
        db, filial, Produto, ProdutoOut,
        ["codigo", "sku", "uuid", "codigo_barras", "nome"], q, limit, offset,
    )


@router.get("/clientes")
def clientes(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    limit: int = Query(default=_LIMITE_CATALOGO, ge=1, le=_LIMITE_CATALOGO),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse:
    return _lista(
        db, filial, Cliente, ClienteOut,
        ["nome_razao", "cpf_cnpj", "email", "telefone", "celular"], q, limit, offset,
    )


@router.get("/funcionarios")
def funcionarios(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    limit: int = Query(default=_LIMITE_CATALOGO, ge=1, le=_LIMITE_CATALOGO),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse:
    return _lista(
        db, filial, Funcionario, FuncionarioOut, ["nome"], q, limit, offset,
    )


class OperadorOut(BaseModel):
    """Projeção mínima de usuário para o filtro de operadores do PDV.

    Expõe apenas id/nome/login — nunca nível, e-mail, tentativas de login ou
    datas de bloqueio (campos do `UsuarioOut` restrito a ADMIN).
    """

    id: int
    nome: str
    login: str


@router.get("/operadores")
def operadores(
    db: DbDep,
    filial: FilialDep,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=_LIMITE_CATALOGO),
    offset: int = Query(default=0, ge=0),
) -> ListaResponse:
    limite = min(max(limit, 1), _LIMITE_CATALOGO)
    desloc = max(offset, 0)
    itens, total = listar(
        db, Usuario, filial_id=filial, q=q,
        campos_busca=["nome", "login"], limit=limite, offset=desloc,
    )
    return ListaResponse(
        data=[OperadorOut(id=u.id, nome=u.nome, login=u.login) for u in itens],
        meta=MetaPaginacao(total=total, limit=limite, offset=desloc),
    )
