"""Rotas de plataforma PRD v3.3: filiais, estações, outbox, diagnóstico, backup.

RBAC: leitura para perfis operacionais; escrita/configuração somente Admin
(filial/papel, estações, backup, termo LGPD). Diagnóstico é Admin.
"""

from fastapi import APIRouter, Depends, Query, Request

from app.deps import DbDep, FilialDep, UsuarioDep, require_nivel
from app.models.enums import NivelAcesso
from app.schemas.common import ItemResponse, ListaResponse, MetaPaginacao
from app.schemas.plataforma import (
    BackupConfigIn,
    BackupConfigOut,
    BackupResultado,
    DiagnosticoOut,
    EstacaoRegistrarIn,
    EstacaoResumo,
    EventoSyncIn,
    EventoSyncOut,
    FilialOut,
    FilialUpdate,
    TermoBackupIn,
    TermoBackupOut,
)
from app.services import (
    backup_service,
    diagnostico_service,
    estacao_service,
    filial_service,
    sync_service,
)
from app.schemas.plataforma import SyncConfigIn, SyncConfigOut, SyncStatusOut

router = APIRouter(prefix="/plataforma", tags=["plataforma"])

admin = Depends(require_nivel(NivelAcesso.ADMIN))


# ------------------------------------------------------------------ filiais


@router.get("/filiais", response_model=list[FilialOut])
def filiais(db: DbDep, filial: FilialDep, _=admin):
    return filial_service.listar(db, filial_id=filial)


@router.put("/filiais/{item_id}", response_model=ItemResponse[FilialOut])
def atualizar_filial(
    item_id: int, payload: FilialUpdate, db: DbDep, filial: FilialDep,
    usuario: UsuarioDep, _=admin,
):
    if item_id != filial:
        # Papel/instalação são da instalação local; não alterar outra filial.
        from fastapi import HTTPException

        raise HTTPException(403, "Só a filial desta instalação pode ser alterada.")
    return ItemResponse(
        data=filial_service.atualizar(
            db, filial_id=item_id, dados=payload.model_dump(exclude_unset=True),
            usuario_id=usuario.id,
        )
    )


# ----------------------------------------------------------------- estações


@router.get("/estacoes", response_model=EstacaoResumo)
def estacoes(db: DbDep, filial: FilialDep, _=admin):
    return estacao_service.listar(db, filial_id=filial)


@router.post("/estacoes/registrar", response_model=ItemResponse[dict])
def registrar_estacao(
    payload: EstacaoRegistrarIn, db: DbDep, filial: FilialDep,
    usuario: UsuarioDep,
):
    # Registro de estação NÃO exige admin: qualquer usuário autenticado
    # registra sua própria estação no primeiro acesso.
    e = estacao_service.registrar(
        db,
        filial_id=filial,
        nome=payload.nome,
        fingerprint=payload.fingerprint,
    )
    return ItemResponse(
        data={"id": e.id, "nome": e.nome, "fingerprint": e.fingerprint[:12]}
    )


@router.delete("/estacoes/{item_id}", status_code=204)
def remover_estacao(
    item_id: int, db: DbDep, filial: FilialDep, _=admin
) -> None:
    estacao_service.remover(db, item_id=item_id, filial_id=filial)


# ------------------------------------------------------------------- outbox


@router.get("/sync/eventos", response_model=ListaResponse[EventoSyncOut])
def eventos_sync(
    db: DbDep,
    filial: FilialDep,
    pendentes: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _=admin,
):
    linhas, total = filial_service.eventos(
        db, filial_id=filial, pendentes=pendentes, limit=limit, offset=offset
    )
    return ListaResponse(
        data=linhas, meta=MetaPaginacao(total=total, limit=limit, offset=offset)
    )


@router.post("/sync/eventos", response_model=ItemResponse[EventoSyncOut], status_code=201)
def criar_evento_sync(
    payload: EventoSyncIn, db: DbDep, filial: FilialDep, _=admin
):
    ev = filial_service.registrar_evento(
        db,
        filial_id=filial,
        entidade=payload.entidade,
        entidade_id=payload.entidade_id,
        operacao=payload.operacao,
        payload=payload.payload,
        uuid=payload.uuid,
    )
    db.commit()
    db.refresh(ev)
    return ItemResponse(data=ev)


@router.post("/sync/marcar-enviados", response_model=ItemResponse[dict])
def marcar_enviados(
    uuids: list[str], db: DbDep, filial: FilialDep, _=admin
):
    n = filial_service.marcar_enviados(db, filial_id=filial, uuids=uuids)
    return ItemResponse(data={"marcados": n})


# ------------------------------------------------------------- sync Neon


@router.get("/sync/config", response_model=ItemResponse[SyncConfigOut])
def sync_config(db: DbDep, filial: FilialDep, _=admin):
    return ItemResponse(
        data={
            "filial_id": filial,
            "configurado": sync_service.configurado(db, filial),
            "url_mascarada": None,
        }
    )


@router.put("/sync/config", response_model=ItemResponse[SyncConfigOut])
def configurar_sync(
    payload: SyncConfigIn, db: DbDep, filial: FilialDep, _=admin
):
    return ItemResponse(
        data=sync_service.registrar_url(db, filial_id=filial, url=payload.url)
    )


@router.get("/sync/status", response_model=ItemResponse[SyncStatusOut])
def status_sync_neon(db: DbDep, filial: FilialDep, _=admin):
    return ItemResponse(data=sync_service.status(db, filial_id=filial))


@router.post("/sync/executar", response_model=ItemResponse[dict])
def executar_sync(db: DbDep, filial: FilialDep, _=admin):
    return ItemResponse(data=sync_service.sincronizar(db, filial_id=filial))


# ------------------------------------------------------------- diagnóstico


@router.get("/diagnostico", response_model=ItemResponse[DiagnosticoOut])
def diagnostico(db: DbDep, _=admin):
    return ItemResponse(data=diagnostico_service.diagnosticar(db))


# ------------------------------------------------------------------- backup


@router.get("/backup", response_model=ItemResponse[BackupConfigOut])
def backup_config(db: DbDep, filial: FilialDep, _=admin):
    return ItemResponse(data=backup_service.obter(db, filial_id=filial))


@router.put("/backup", response_model=ItemResponse[BackupConfigOut])
def configurar_backup(
    payload: BackupConfigIn, db: DbDep, filial: FilialDep, _=admin
):
    return ItemResponse(
        data=backup_service.configurar(
            db, filial_id=filial, dados=payload.model_dump(exclude_unset=True)
        )
    )


@router.post("/backup/executar", response_model=ItemResponse[BackupResultado])
def executar_backup(
    db: DbDep, filial: FilialDep, usuario: UsuarioDep, _=admin
):
    return ItemResponse(
        data=backup_service.executar_backup(db, filial_id=filial, usuario_id=usuario.id)
    )


@router.get("/backup/termo", response_model=ItemResponse[TermoBackupOut])
def termo_backup(db: DbDep, filial: FilialDep, _=admin):
    return ItemResponse(data=backup_service.termo(db, filial_id=filial))


@router.post("/backup/termo", response_model=ItemResponse[TermoBackupOut])
def aceitar_termo(
    payload: TermoBackupIn,
    request: Request,
    db: DbDep,
    filial: FilialDep,
    usuario: UsuarioDep,
    _=admin,
):
    ip = request.client.host if request.client else None
    return ItemResponse(
        data=backup_service.aceitar_termo(
            db, filial_id=filial, usuario_id=usuario.id,
            aceito=payload.aceito, versao=payload.versao, ip=ip,
        )
    )


@router.post("/backup/rotacionar", response_model=ItemResponse[dict])
def rotacionar_backup(db: DbDep, filial: FilialDep, _=admin):
    n = backup_service.rotacionar(db, filial_id=filial)
    return ItemResponse(data={"removidos": n})


def registrar(api: APIRouter) -> None:
    api.include_router(router)
