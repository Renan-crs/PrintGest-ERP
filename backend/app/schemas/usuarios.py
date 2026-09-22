"""Schemas Pydantic de usuários e gestão de acesso."""

from datetime import datetime

from pydantic import Field

from app.models.enums import NivelAcesso
from app.schemas.common import ORMModel


class UsuarioCreate(ORMModel):
    nome: str = Field(min_length=1, max_length=120)
    login: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.-]+$")
    senha: str = Field(min_length=4, max_length=128)
    email: str | None = Field(default=None, max_length=120)
    nivel_acesso: NivelAcesso = NivelAcesso.OPERADOR
    filial_id: int | None = None
    ativo: bool = True


class UsuarioUpdate(ORMModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=120)
    nivel_acesso: NivelAcesso | None = None
    filial_id: int | None = None
    ativo: bool | None = None
    senha: str | None = Field(default=None, min_length=4, max_length=128)


class UsuarioOut(ORMModel):
    id: int
    filial_id: int | None
    nome: str
    login: str
    email: str | None
    nivel_acesso: NivelAcesso
    ativo: bool
    falhas_login: int
    bloqueado_em: datetime | None
    ultimo_login: datetime | None
    created_at: datetime
    updated_at: datetime