"""Routers de licenciamento — ativação, renovação e situação (PRD §3/§7).

Rotas liberadas no modo de leitura (o middleware de licença as exclui do 423):
- `GET /v1/licenca` — situação atual (sem autenticação quando em modo leitura);
- `POST /v1/licenca/ativar` — troca CNPJ + código por licença ativa;
- `POST /v1/licenca/renovar` — força a renovação do token via `/validar`.
"""

from fastapi import APIRouter

from app.deps import DbDep
from app.schemas import ItemResponse
from app.schemas.licenca import LicencaAtivarIn, LicencaSituacaoOut
from app.services import licensa_service

router = APIRouter(prefix="/licenca", tags=["licenciamento"])


@router.get("")
def situacao(db: DbDep) -> ItemResponse[LicencaSituacaoOut]:
    return ItemResponse(data=licensa_service.situacao(db))


@router.post("/ativar")
def ativar(body: LicencaAtivarIn, db: DbDep) -> ItemResponse[LicencaSituacaoOut]:
    return ItemResponse(
        data=licensa_service.ativar(
            db, cnpj=body.cnpj, codigo_licenca=body.codigo_licenca
        )
    )


@router.post("/renovar")
def renovar(db: DbDep) -> ItemResponse[LicencaSituacaoOut]:
    return ItemResponse(data=licensa_service.renovar(db))