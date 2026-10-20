"""Schemas de licenciamento - chave de produto validada online (RedGest)."""

from datetime import datetime

from pydantic import BaseModel, Field


class LicencaAtivarIn(BaseModel):
    chave_ativacao: str | None = Field(
        default=None,
        max_length=32,
        description=(
            "Chave de produto entregue na contratação (XXXX-XXXX-XXXX-XXXX) — "
            "Contrato C. Aceita com ou sem hífens; o servidor normaliza antes de "
            "validar. No Contrato B a ativação usa `cnpj` + `codigo_licenca`."
        ),
    )
    cnpj: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Contrato B: CNPJ do cliente titular da licença (14 dígitos; aceita "
            "com ou sem máscara). O servidor normaliza antes de enviar."
        ),
    )
    codigo_licenca: str | None = Field(
        default=None,
        max_length=64,
        description=(
            "Contrato B: código da licença (o UUID emitido pelo RedGest). "
            "Corresponde ao valor entregue no e-mail de emissão."
        ),
    )


class LicencaSituacaoOut(BaseModel):
    sistema: str
    # Contrato em uso: `c` (chave de produto v3.6) ou `b` (Licenca v4.0).
    contrato: str = "c"
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
