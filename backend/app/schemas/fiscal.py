"""Schemas do módulo Fiscal (PRD §1.3 / telas_e_fluxos §1.6).

O PrintGest não transmite NF-e/NFC-e/NFS-e: ele monta o payload a partir de
uma venda/OS e repassa a um **gateway fiscal de terceiro** configurado na
instalação. Este módulo expõe emissão, consulta, cancelamento, eventos de
auditoria e o panorama da tela de contingência.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import ModeloFiscal, StatusFiscal
from app.schemas.common import ORMModel


class DocumentoFiscalOut(ORMModel):
    id: int
    filial_id: int
    modelo: ModeloFiscal
    gateway: str | None = None
    gateway_id: str | None = None
    ambiente: str = "homologacao"
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
    ultima_consulta_em: datetime | None = None
    cancelado_em: datetime | None = None
    motivo_cancelamento: str | None = None
    criado_por: int | None = None
    ibs_cbs_snapshot: dict | None = None
    created_at: datetime
    updated_at: datetime


class FiscalEmitirIn(BaseModel):
    """Emissão a partir de uma venda de balcão ou de uma O.S.

    Exatamente uma das duas origens deve ser informada. `modelo` é obrigatório
    porque a mesma origem pode gerar NFC-e (balcão) ou NFS-e (serviço).
    """

    modelo: ModeloFiscal
    venda_balcao_id: int | None = None
    ordem_servico_id: int | None = None
    contingencia: bool = False


class FiscalCancelarIn(BaseModel):
    motivo: str = Field(min_length=1, max_length=500)


class FiscalEventoOut(ORMModel):
    id: int
    filial_id: int
    documento_fiscal_id: int | None = None
    tipo: str
    mensagem: str | None = None
    detalhes: dict | None = None
    criado_por: int | None = None
    created_at: datetime


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
    gateway_url: str | None = None
    ambiente: str = "homologacao"
    ibs_cbs_parametrizado: bool = False
