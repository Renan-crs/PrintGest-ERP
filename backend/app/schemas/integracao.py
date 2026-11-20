"""Schemas de integrações com apps de terceiros (PRD v3.3 §3.6).

NENHUM schema de entrada/saída expõe a credencial em claro: o valor gravado
no cofre só aparece mascarado (`credencial_mascara`) com um indicador booleano.
O campo de escrita é writeOnly — nunca serializado de volta.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import TipoIntegracao
from app.schemas.common import MetaPaginacao, ORMModel


def _url_valida(valor: str | None) -> str | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    if not texto.lower().startswith(("http://", "https://")):
        raise ValueError("A URL deve começar com http:// ou https://.")
    return texto


class IntegracaoOut(ORMModel):
    id: int
    filial_id: int
    tipo: TipoIntegracao
    nome: str
    provedor: str | None = None
    base_url: str | None = None
    auth_header: str
    auth_prefix: str
    ambiente: str
    ativo: bool
    opcoes: dict | None = None
    credencial_mascara: str | None = None
    certificado_mascara: str | None = None
    tem_credencial: bool
    tem_certificado: bool
    ultimo_teste_em: datetime | None = None
    ultimo_teste_ok: bool | None = None
    created_at: datetime
    updated_at: datetime


class IntegracaoCreate(BaseModel):
    tipo: TipoIntegracao
    nome: str = Field(min_length=1, max_length=120)
    provedor: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    auth_header: str = Field(default="Authorization", max_length=80)
    auth_prefix: str = Field(default="Bearer ", max_length=40)
    ambiente: str = Field(default="homologacao", max_length=20)
    ativo: bool = True
    opcoes: dict | None = None
    # Segredos: writeOnly — nunca aparecem em respostas.
    credencial: str | None = Field(default=None, writeOnly=True, max_length=4000)
    certificado: str | None = Field(default=None, writeOnly=True, max_length=20000)

    @field_validator("base_url")
    @classmethod
    def _validar_url(cls, valor):
        return _url_valida(valor)

    @field_validator("ambiente")
    @classmethod
    def _validar_ambiente(cls, valor):
        texto = (valor or "").strip().lower()
        if texto not in {"homologacao", "producao"}:
            raise ValueError("ambiente deve ser 'homologacao' ou 'producao'.")
        return texto


class IntegracaoUpdate(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    provedor: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=500)
    auth_header: str | None = Field(default=None, max_length=80)
    auth_prefix: str | None = Field(default=None, max_length=40)
    ambiente: str | None = Field(default=None, max_length=20)
    ativo: bool | None = None
    opcoes: dict | None = None
    credencial: str | None = Field(default=None, writeOnly=True, max_length=4000)
    certificado: str | None = Field(default=None, writeOnly=True, max_length=20000)
    # True = apaga a credencial/certificado gravado no cofre.
    remover_credencial: bool = False
    remover_certificado: bool = False

    @field_validator("base_url")
    @classmethod
    def _validar_url(cls, valor):
        return _url_valida(valor)

    @field_validator("ambiente")
    @classmethod
    def _validar_ambiente(cls, valor):
        if valor is None:
            return None
        texto = valor.strip().lower()
        if texto not in {"homologacao", "producao"}:
            raise ValueError("ambiente deve ser 'homologacao' ou 'producao'.")
        return texto


class IntegracaoTesteOut(BaseModel):
    ok: bool
    status_http: int | None = None
    mensagem: str
    testado_em: datetime
    # Confirma que o segredo NÃO é devolvido:
    segredo_exposto: bool = False


class IntegracaoEventoOut(ORMModel):
    id: int
    filial_id: int
    integracao_id: int | None = None
    tipo: str
    mensagem: str | None = None
    detalhes: dict | None = None
    criado_por: int | None = None
    created_at: datetime


class ListaIntegracoes(BaseModel):
    data: list[IntegracaoOut]
    total: int
    # `total` no topo é mantido por compatibilidade; `meta` segue a convenção
    # das demais listagens e é o que o cliente desktop consome (`_paginar`).
    meta: MetaPaginacao | None = None
