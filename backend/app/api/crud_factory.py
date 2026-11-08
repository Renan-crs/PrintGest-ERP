"""Fábrica de rotas CRUD — evita repetição entre as telas de cadastro.

Padrão por endpoint:
  GET    /v1/<entidade>       lista paginada com busca rápida (?q=, limit, offset)
  GET    /v1/<entidade>/{id}  detalhe
  POST   /v1/<entidade>       criar
  PUT    /v1/<entidade>/{id}  atualizar
  DELETE /v1/<entidade>/{id}  desativar (soft delete)

Payloads são validados pelos schemas Pydantic de Create/Update antes de persistir.
RBAC: o menor nível informado é exigido em todas as rotas do router (via Depends).
"""

from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.deps import DbDep, FilialDep
from app.models.enums import NivelAcesso
from app.schemas import ItemResponse, ListaResponse
from app.schemas.common import MetaPaginacao
from app.services.crud import atualizar, buscar_por_id, criar, desativar, listar

ModelT = TypeVar("ModelT")
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)
OutT = TypeVar("OutT", bound=BaseModel)


def _normalizar(filial_id: int, dados: dict[str, Any]) -> dict[str, Any]:
    """Cadastros pertencem à filial efetiva do usuário — o cliente não escolhe a filial."""
    dados["filial_id"] = filial_id
    return dados


def criar_router_crud(
    *,
    prefix: str,
    model: type[ModelT],
    schema_in: type[CreateT],
    schema_update: type[UpdateT],
    schema_out: type[OutT],
    campos_busca: list[str],
    campos_filtro: list[str] | None = None,
    tags: list[str],
    nivel_acesso: NivelAcesso = NivelAcesso.OPERADOR,
) -> APIRouter:
    from app.deps import require_nivel

    router = APIRouter(
        prefix=prefix,
        tags=tags,
        dependencies=[Depends(require_nivel(nivel_acesso))],
    )

    def _out(item: ModelT) -> OutT:
        return schema_out.model_validate(item)

    @router.get("")
    def lista(
        request: Request,
        db: DbDep,
        filial: FilialDep,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ListaResponse[OutT]:
        limite = min(max(limit, 1), 200)
        desloc = max(offset, 0)
        # Filtros por campo (ex.: `tipo_pessoa=pj`); só os campos declarados na
        # rota são aceitos — campos desconhecidos são ignorados (whitelist).
        filtros = {}
        for campo in campos_filtro or []:
            valor = request.query_params.get(campo)
            if valor is not None and valor.strip():
                filtros[campo] = valor.strip()
        itens, total = listar(
            db,
            model,
            filial_id=filial,
            q=q,
            campos_busca=campos_busca,
            filtros=filtros,
            limit=limite,
            offset=desloc,
        )
        return ListaResponse(
            data=[_out(i) for i in itens],
            meta=MetaPaginacao(total=total, limit=limite, offset=desloc),
        )

    @router.get("/{item_id}")
    def detalhe(item_id: int, db: DbDep, filial: FilialDep) -> ItemResponse[OutT]:
        return ItemResponse(
            data=_out(buscar_por_id(db, model, item_id, filial_id=filial))
        )

    @router.post("")
    def criar_item(
        body: schema_in,
        db: DbDep,
        filial: FilialDep,  # type: ignore[valid-type]
    ) -> ItemResponse[OutT]:
        return ItemResponse(
            data=_out(criar(db, model, _normalizar(filial, body.model_dump())))
        )

    @router.put("/{item_id}")
    def atualizar_item(
        item_id: int,
        body: schema_update,
        db: DbDep,
        filial: FilialDep,  # type: ignore[valid-type]
    ) -> ItemResponse[OutT]:
        dados = body.model_dump(exclude_unset=True)
        if not dados:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum dado recebido para atualização.",
            )
        return ItemResponse(
            data=_out(atualizar(db, model, item_id, dados, filial_id=filial))
        )

    @router.delete("/{item_id}", status_code=204)
    def remover(item_id: int, db: DbDep, filial: FilialDep) -> None:
        desativar(db, model, item_id, filial_id=filial)

    return router
