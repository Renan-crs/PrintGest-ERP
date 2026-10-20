"""Routers de licenciamento - licença validada online (PRD §3/§7).

Dois contratos convivem (a flag `PRINTGEST_REDGEST_CONTRATO` escolhe):

- **Contrato C** (default): o usuário digita a **chave de produto** na primeira
  execução e ela é validada online em `/api/v1/licencas-software/validar/`.
- **Contrato B** (`Licenca` v4.0, `docs/migracao_redgest_v4.md`): o usuário
  informa **CNPJ + código da licença** e o `licensa_service` faz o handshake em
  `/api/v1/licencas/{uuid}/ativar/`, guardando `client_id`/`client_secret`.

Rotas liberadas no modo de leitura (o middleware de licença as exclui do 423):
- `GET /v1/licenca` — situação atual (sem autenticação quando em modo leitura);
- `POST /v1/licenca/ativar` — ativa a instalação no contrato configurado;
- `POST /v1/licenca/renovar` — força uma revalidação online da licença.
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
            db,
            chave_ativacao=body.chave_ativacao or "",
            cnpj=body.cnpj or "",
            codigo_licenca=body.codigo_licenca or "",
        )
    )


@router.post("/renovar")
def renovar(db: DbDep) -> ItemResponse[LicencaSituacaoOut]:
    return ItemResponse(data=licensa_service.renovar(db))
