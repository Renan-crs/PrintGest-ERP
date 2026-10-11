"""Schemas do módulo Fiscal (PRD §1.3 / telas_e_fluxos §1.6).

A **emissão** de NF-e/NFC-e depende de um gateway fiscal externo (Focus NFe,
PlugNotas, eNotas…) que não faz parte deste repositório nem do `schema.sql`.
Este módulo entrega o que é possível sem o gateway: **consulta** dos documentos
fiscais e a **tela de contingência** (aviso + pendências).
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import ModeloFiscal, StatusFiscal
from app.schemas.common import ORMModel


class DocumentoFiscalOut(ORMModel):
    id: int
    filial_id: int
    modelo: ModeloFiscal
    numero: int | None = None
    serie: int | None = None
    chave_acesso: str | None = None
    status: StatusFiscal
    venda_balcao_id: int | None = None
    ordem_servico_id: int | None = None
    cliente_id: int | None = None
    cliente_nome: str | None = None
    valor_nota: Decimal
    xml_path: str | None = None
    danfe_path: str | None = None
    protocolo: str | None = None
    mensagem_retorno: str | None = None
    contingencia: bool
    tentativas: int
    criado_por: int | None = None
    created_at: datetime
    updated_at: datetime


class ResumoFiscal(BaseModel):
    """Panorama para a tela de Contingência (contagens por status/modelo)."""

    total: int
    por_status: dict[str, int]
    por_modelo: dict[str, int]
    pendentes: int
    em_contingencia: int
    gateway_configurado: bool
    gateway_disponivel: bool
    mensagem: str
