"""Schemas de autenticação e sessão."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import NivelAcesso
from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=60)
    senha: str = Field(min_length=1, max_length=128)


class PrimeiroAcessoIn(BaseModel):
    """Define a senha de um usuário que ainda está em primeiro acesso."""

    login: str = Field(min_length=1, max_length=60)
    nova_senha: str = Field(min_length=8, max_length=128)


class UsuarioSessaoOut(ORMModel):
    id: int
    nome: str
    login: str
    nivel_acesso: NivelAcesso
    filial_id: int | None = None


class LoginOut(BaseModel):
    token: str
    tipo: str = "bearer"
    expira_em: datetime
    usuario: UsuarioSessaoOut


class TrocarSenhaIn(BaseModel):
    senha_atual: str = Field(min_length=1, max_length=128)
    nova_senha: str = Field(min_length=8, max_length=128)