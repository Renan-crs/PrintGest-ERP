"""Routers de licenciamento - chave de produto validada online (PRD §3/§7).

Fluxo RedGest Contrato C: o usuário digita a **chave de produto** na primeira
execução e ela é validada online em `/api/v1/licencas-software/validar/`.

Rotas liberadas no modo de leitura (o middleware de licença as exclui do 423):
- `GET /v1/licenca` — situação atual (sem autenticação quando em modo leitura);
- `POST /v1/licenca/ativar` — valida a chave de produto e ativa a instalação;
- `POST /v1/licenca/renovar` — força uma revalidação online da chave.
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
        data=licensa_service.ativar(db, chave_ativacao=body.chave_ativacao)
    )


@router.post("/renovar")
def renovar(db: DbDep) -> ItemResponse[LicencaSituacaoOut]:
    return ItemResponse(data=licensa_service.renovar(db))
