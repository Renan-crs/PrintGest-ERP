"""Schemas do módulo Agendamento (PRD §1.3 / telas_e_fluxos §1.3 — Calendário/Lista).

A tabela `agendamento` já existe no `schema.sql` (baseline Fase 1): compromissos
de **produção** e **entrega**, com horário de início/fim, status e vínculo
opcional com uma O.S. (`ordem_servico_id`). Estes schemas expõem exatamente
esses campos — nenhum campo novo.
"""

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.enums import StatusAgenda, TipoAgenda
from app.schemas.common import ORMModel


class AgendamentoCreate(BaseModel):
    titulo: str
    descricao: str | None = None
    tipo: TipoAgenda = TipoAgenda.PRODUCAO
    data_hora_inicio: datetime
    data_hora_fim: datetime | None = None
    ordem_servico_id: int | None = None
    status: StatusAgenda = StatusAgenda.AGENDADO

    @field_validator("titulo")
    @classmethod
    def _titulo_nao_vazio(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Informe o título do agendamento.")
        return valor

    @field_validator("data_hora_fim")
    @classmethod
    def _fim_apos_inicio(cls, valor: datetime | None, info) -> datetime | None:
        inicio = info.data.get("data_hora_inicio")
        if valor is not None and inicio is not None and valor < inicio:
            raise ValueError("O término deve ser igual ou posterior ao início.")
        return valor


class AgendamentoUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    tipo: TipoAgenda | None = None
    data_hora_inicio: datetime | None = None
    data_hora_fim: datetime | None = None
    ordem_servico_id: int | None = None
    status: StatusAgenda | None = None

    @field_validator("titulo")
    @classmethod
    def _titulo_nao_vazio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("Informe o título do agendamento.")
        return valor


class AgendamentoOut(ORMModel):
    id: int
    filial_id: int
    tipo: TipoAgenda
    status: StatusAgenda
    titulo: str
    descricao: str | None = None
    data_hora_inicio: datetime
    data_hora_fim: datetime | None = None
    ordem_servico_id: int | None = None
    ordem_servico_numero: int | None = None
    ordem_servico_cliente: str | None = None
    usuario_id: int | None = None
    created_at: datetime
    updated_at: datetime
