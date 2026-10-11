"""Schemas do módulo Configuração (PRD §1.8 / telas_e_fluxos §1.8, §2.6).

Reúne **Dados da Empresa / Personalização** (tabela `empresa`) e o **Reajuste de
Preços em Bloco** (tabela `preco_reajuste_historico`). O reajuste sempre passa
por **simulação** antes de aplicar e exige a **senha** do administrador — a
trilha de auditoria (quem, quando, valores antigos e novos) é gravada em
`preco_reajuste_historico.detalhes`.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EmpresaOut(ORMModel):
    id: int
    razao_social: str
    nome_fantasia: str | None = None
    cnpj: str
    inscricao_estadual: str | None = None
    inscricao_municipal: str | None = None
    regime_tributario: str | None = None
    ambiente_fiscal: str
    cnae_fiscal: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    cep: str | None = None
    telefone: str | None = None
    email: str | None = None
    website: str | None = None
    logotipo_path: str | None = None
    fundo_tela_path: str | None = None
    impressora_matricial: str | None = None
    impressora_cupom: str | None = None
    certificado_path: str | None = None
    ativa: bool


class EmpresaUpdate(BaseModel):
    """Atualização parcial dos Dados da Empresa / Personalização.

    Todos os campos são opcionais e só os enviados são alterados
    (`exclude_unset`), permitindo que a tela de Personalização atualize apenas
    logotipo/fundo/impressoras sem reenviar o cadastro fiscal inteiro.
    """

    razao_social: str | None = Field(default=None, min_length=1, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=120)
    cnpj: str | None = Field(default=None, min_length=14, max_length=14)
    inscricao_estadual: str | None = Field(default=None, max_length=20)
    inscricao_municipal: str | None = Field(default=None, max_length=20)
    regime_tributario: str | None = Field(default=None, max_length=60)
    ambiente_fiscal: str | None = Field(default=None, min_length=1, max_length=1)
    cnae_fiscal: str | None = Field(default=None, max_length=10)
    logradouro: str | None = Field(default=None, max_length=160)
    numero: str | None = Field(default=None, max_length=12)
    complemento: str | None = Field(default=None, max_length=80)
    bairro: str | None = Field(default=None, max_length=80)
    cidade: str | None = Field(default=None, max_length=80)
    uf: str | None = Field(default=None, max_length=2)
    cep: str | None = Field(default=None, max_length=8)
    telefone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=160)
    logotipo_path: str | None = Field(default=None, max_length=500)
    fundo_tela_path: str | None = Field(default=None, max_length=500)
    impressora_matricial: str | None = Field(default=None, max_length=160)
    impressora_cupom: str | None = Field(default=None, max_length=160)


class ReajusteSimulacaoIn(BaseModel):
    """Critério e magnitude do reajuste (compartilhado por simular/aplicar)."""

    criterio: Literal["todos", "categoria"] = "todos"
    categoria_id: int | None = None
    tipo_reajuste: Literal["percentual", "valor_fixo"] = "percentual"
    valor: Decimal = Field(ge=0)


class ReajusteAplicarIn(ReajusteSimulacaoIn):
    """Confirmação do reajuste: exige a senha do admin autenticado (§2.6)."""

    senha: str = Field(min_length=1, max_length=128)


class ReajusteItemOut(BaseModel):
    produto_id: int
    codigo: str
    nome: str
    preco_antes: Decimal
    preco_depois: Decimal


class ReajusteSimulacaoOut(BaseModel):
    """Prévia do reajuste. `afetados` é o total elegível; `itens` pode vir
    limitado (a UI mostra os primeiros e resume o restante)."""

    total: int
    afetados: int
    bloqueados: int
    itens: list[ReajusteItemOut]


class ReajusteResultadoOut(BaseModel):
    historico_id: int
    afetados: int
    executado_em: datetime


class ReajusteHistoricoOut(ORMModel):
    id: int
    usuario_id: int
    tipo_reajuste: str
    valor_reajuste: Decimal
    criterio: str
    itens_afetados: int
    executado_em: datetime
