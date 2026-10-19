"""Schemas de licenciamento - chave de produto validada online (RedGest)."""

from datetime import datetime

from pydantic import BaseModel, Field


class LicencaAtivarIn(BaseModel):
    chave_ativacao: str = Field(
        min_length=1,
        max_length=32,
        description=(
            "Chave de produto entregue na contratação (XXXX-XXXX-XXXX-XXXX). "
            "Aceita com ou sem hífens; o servidor normaliza antes de validar."
        ),
    )


class LicencaSituacaoOut(BaseModel):
    sistema: str
    chave: str | None = None
    plano: str | None = None
    status: str
    # Estado derivado: ativa | tolerancia | leitura | revogada | nao_ativada.
    estado: str
    motivo: str
    modo_leitura: bool
    expira_em: datetime | None = None
    tolerancia_expira_em: datetime | None = None
    limite_ativacoes: int | None = None
    ativacoes_realizadas: int | None = None
    ultima_validacao: datetime | None = None
    ultima_tentativa_em: datetime | None = None
    ultimo_erro: str | None = None
