"""Schemas de filiais, estações, outbox, diagnóstico e backup (PRD v3.3)."""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ------------------------------------------------------------------ filiais


class FilialOut(ORMModel):
    id: int
    empresa_id: int
    nome: str
    cnpj: str | None = None
    instalacao_id: str | None = None
    papel: str | None = None
    ativa: bool
    criada_em: datetime | None = None


class FilialUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    ativa: bool | None = None
    instalacao_id: str | None = Field(default=None, max_length=40)
    papel: str | None = Field(default=None, max_length=10)


# ----------------------------------------------------------------- estações


class EstacaoOut(ORMModel):
    id: int
    filial_id: int
    nome: str
    fingerprint: str
    ultimo_acesso: datetime
    criado_em: datetime
    ativa: bool = True
    dias_inativa: int = 0


class EstacaoRegistrarIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    fingerprint: str = Field(min_length=8, max_length=64)


class EstacaoResumo(BaseModel):
    total: int
    limite: int
    vagas: int
    estacoes: list[EstacaoOut] = Field(default_factory=list)


# ------------------------------------------------------------------- outbox


class EventoSyncOut(ORMModel):
    id: int
    uuid: str
    filial_id: int
    entidade: str
    entidade_id: int | None = None
    operacao: str
    seq: int
    criado_em: datetime
    enviado_em: datetime | None = None


class EventoSyncIn(BaseModel):
    entidade: str = Field(min_length=1, max_length=60)
    entidade_id: int | None = None
    operacao: str = Field(min_length=1, max_length=20)
    payload: dict = Field(default_factory=dict)
    uuid: str = Field(default_factory=lambda: str(uuid4()))


# -------------------------------------------------------------- diagnóstico


class LicencaEventoOut(ORMModel):
    id: int
    em: datetime
    tipo: str
    estado_anterior: str | None = None
    estado_novo: str | None = None
    codigo_erro: str | None = None
    correlation_id: str | None = None
    detalhe: dict | None = None


class DiagnosticoOut(BaseModel):
    estado: str
    modo_leitura: bool
    plano: str | None = None
    status_servidor: str | None = None
    estado_vinculo: str | None = None
    token_exp: datetime | None = None
    grace_deadline: datetime | None = None
    proxima_renovacao: datetime | None = None
    ultima_renovacao_ok: datetime | None = None
    ultima_tentativa_em: datetime | None = None
    falhas_seguidas: int = 0
    rebinds_restantes: int | None = None
    vagas_livres: int | None = None
    max_estacoes: int | None = None
    max_filiais: int | None = None
    modulos_habilitados: list[str] = Field(default_factory=list)
    instalacao_id: str | None = None
    instalacao_nome: str | None = None
    papel: str | None = None
    licenca_id: str | None = None
    diferenca_relogio_segundos: int | None = None
    versao: str
    correlation_ids: list[str] = Field(default_factory=list)
    eventos: list[LicencaEventoOut] = Field(default_factory=list)
    # Nunca preenchido com valor real (RF-DG-02 / RF-SG-04).
    segredos_mascarados: bool = True


# ------------------------------------------------------------------- backup


class BackupConfigOut(ORMModel):
    id: int
    filial_id: int
    horario: str
    retencao_dias: int
    destino: str | None = None
    neon_espelho: bool
    ultimo_backup_em: datetime | None = None
    ultimo_backup_ok: bool | None = None
    ultimo_backup_tamanho: int | None = None
    ultimo_envio_neon_em: datetime | None = None
    ultimo_envio_neon_ok: bool | None = None


class BackupConfigIn(BaseModel):
    horario: str | None = Field(default=None, max_length=5)
    retencao_dias: int | None = Field(default=None, ge=1, le=365)
    destino: str | None = Field(default=None, max_length=500)
    neon_espelho: bool | None = None


class BackupResultado(BaseModel):
    ok: bool
    caminho: str | None = None
    tamanho: int | None = None
    mensagem: str
    executado_em: datetime


class TermoBackupIn(BaseModel):
    aceito: bool
    versao: str = Field(default="1.0", max_length=20)


class TermoBackupOut(ORMModel):
    id: int | None = None
    filial_id: int | None = None
    versao: str
    aceito: bool
    aceito_em: datetime | None = None
    usuario_id: int | None = None
