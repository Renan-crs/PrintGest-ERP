"""Schemas de licenciamento — ativação e situação (`online_periodic`)."""

from datetime import datetime

from pydantic import BaseModel, Field


class LicencaAtivarIn(BaseModel):
    cnpj: str = Field(min_length=1, description="CNPJ da gráfica (aceita máscara).")
    codigo_licenca: str = Field(min_length=1, max_length=40)


class LicencaSituacaoOut(BaseModel):
    sistema: str
    cnpj: str | None = None
    codigo_licenca: str | None = None
    plano: str | None = None
    status: str
    modo_leitura: bool
    max_estacoes: int | None = None
    modulos_habilitados: list[str] = []
    token_expira_em: datetime | None = None