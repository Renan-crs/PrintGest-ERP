"""Schemas do módulo Projetos (PRD Módulo Projetos — Quadro Kanban).

Expostos sob `/v1/projetos` (namespace novo, aditivo). O contrato espelha o
modelo de dados da §9 e as regras de visibilidade das §PV1–PV6:

- `posicao` é ordenação **fracionária** (§10). A API, porém, aceita e devolve
  um **índice** (0-based) de destino, para o cliente não precisar calcular
  frações; o servidor converte o índice em fração e renumera a lista quando o
  espaço acaba.
- `versao` sustenta o controle otimista de edição (§10): envie o valor lido e
  recebe 409 se outro usuário gravou primeiro.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import OrigemMembro, StatusOs, TipoLista
from app.schemas.common import ORMModel


class ListaCreate(BaseModel):
    nome: str
    tipo: TipoLista = TipoLista.LIVRE
    status_os: StatusOs | None = None
    usuario_dono_id: int | None = None
    fornecedor_id: int | None = None
    posicao: int | None = None  # índice (0-based) de inserção; padrão = final

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Informe o nome da lista.")
        return valor


class ListaUpdate(BaseModel):
    nome: str | None = None
    tipo: TipoLista | None = None
    status_os: StatusOs | None = None
    usuario_dono_id: int | None = None
    fornecedor_id: int | None = None
    posicao: int | None = None  # índice (0-base) de destino ao reordenar

    @field_validator("nome")
    @classmethod
    def _nome_nao_vazio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("Informe o nome da lista.")
        return valor


class ListaOut(ORMModel):
    id: int
    quadro_id: int
    nome: str
    posicao: Decimal
    tipo: TipoLista
    status_os: StatusOs | None = None
    usuario_dono_id: int | None = None
    usuario_dono_nome: str | None = None
    fornecedor_id: int | None = None
    arquivada: bool
    # PV5: a contagem respeita a visibilidade do usuário consultante.
    contagem: int = 0


class QuadroOut(BaseModel):
    id: int
    filial_id: int
    nome: str
    listas: list[ListaOut]


class MembroOut(BaseModel):
    usuario_id: int
    nome: str
    origem: OrigemMembro


class CartaoCreate(BaseModel):
    lista_id: int
    titulo: str
    descricao: str | None = None
    data_inicio: date | None = None
    data_entrega: date | None = None
    lembrete_min: int | None = None

    @field_validator("titulo")
    @classmethod
    def _titulo_nao_vazio(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Informe o título do cartão.")
        return valor


class CartaoUpdate(BaseModel):
    versao: int
    titulo: str | None = None
    descricao: str | None = None
    data_inicio: date | None = None
    data_entrega: date | None = None
    lembrete_min: int | None = None
    concluido: bool | None = None

    @field_validator("titulo")
    @classmethod
    def _titulo_nao_vazio(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("Informe o título do cartão.")
        return valor


class MoverCartaoIn(BaseModel):
    versao: int
    lista_id: int
    posicao: int = 0  # índice (0-based) de destino na lista alvo


class VersaoIn(BaseModel):
    """Corpo das ações que só exigem a versão lida (arquivar/restaurar)."""

    versao: int


class AtribuirCartaoIn(BaseModel):
    versao: int
    usuario_id: int


class MembroIn(BaseModel):
    usuario_id: int


class CartaoOut(ORMModel):
    id: int
    filial_id: int
    lista_id: int
    posicao: Decimal
    titulo: str
    descricao: str | None = None
    data_inicio: date | None = None
    data_entrega: date | None = None
    lembrete_min: int | None = None
    concluido: bool
    concluido_em: datetime | None = None
    ordem_servico_id: int | None = None
    ultimo_responsavel_id: int | None = None
    ultimo_responsavel_nome: str | None = None
    terceiro_fornecedor_id: int | None = None
    terceiro_prazo: date | None = None
    terceiro_custo: Decimal | None = None
    arquivado: bool
    versao: int
    membros: list[MembroOut] = Field(default_factory=list)
    # Fase 2 (Cartão rico): etiquetas aplicadas e selos de progresso (RF4).
    etiquetas: list["EtiquetaOut"] = Field(default_factory=list)
    checklist_total: int = 0
    checklist_concluidos: int = 0
    comentarios_total: int = 0
    criado_por: int | None = None
    criado_em: datetime
    atualizado_em: datetime


# ---------------------------------------------------------- Fase 2: etiquetas


class EtiquetaCreate(BaseModel):
    nome: str | None = None
    cor: str

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None

    @field_validator("cor")
    @classmethod
    def _cor(cls, valor: str) -> str:
        return _validar_cor(valor)


class EtiquetaUpdate(BaseModel):
    nome: str | None = None
    cor: str | None = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        return valor.strip() or None

    @field_validator("cor")
    @classmethod
    def _cor(cls, valor: str | None) -> str | None:
        return None if valor is None else _validar_cor(valor)


class EtiquetaOut(ORMModel):
    id: int
    filial_id: int
    nome: str | None = None
    cor: str


class EtiquetaAplicarIn(BaseModel):
    etiqueta_id: int


# --------------------------------------------------------- Fase 2: checklist


class ChecklistCreate(BaseModel):
    titulo: str

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Informe o título do checklist.")
        return valor


class ChecklistUpdate(BaseModel):
    titulo: str | None = None
    posicao: int | None = None  # índice (0-based) de reordenação

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("Informe o título do checklist.")
        return valor


class ChecklistItemCreate(BaseModel):
    texto: str
    responsavel_id: int | None = None
    data_entrega: date | None = None

    @field_validator("texto")
    @classmethod
    def _texto(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Informe o texto do item.")
        return valor


class ChecklistItemUpdate(BaseModel):
    texto: str | None = None
    concluido: bool | None = None
    responsavel_id: int | None = None
    data_entrega: date | None = None
    posicao: int | None = None  # índice (0-based) de reordenação

    @field_validator("texto")
    @classmethod
    def _texto(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = valor.strip()
        if not valor:
            raise ValueError("Informe o texto do item.")
        return valor


class ChecklistItemOut(ORMModel):
    id: int
    checklist_id: int
    texto: str
    concluido: bool
    responsavel_id: int | None = None
    responsavel_nome: str | None = None
    data_entrega: date | None = None
    posicao: Decimal


class ChecklistOut(ORMModel):
    id: int
    cartao_id: int
    titulo: str
    posicao: Decimal
    total: int = 0
    concluidos: int = 0
    itens: list[ChecklistItemOut] = Field(default_factory=list)


# -------------------------------------------------------- Fase 2: comentários


class ComentarioCreate(BaseModel):
    texto: str
    resposta_a_id: int | None = None

    @field_validator("texto")
    @classmethod
    def _texto(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Escreva um comentário.")
        return valor


class ComentarioUpdate(BaseModel):
    texto: str

    @field_validator("texto")
    @classmethod
    def _texto(cls, valor: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            raise ValueError("Escreva um comentário.")
        return valor


class ComentarioOut(ORMModel):
    id: int
    cartao_id: int
    usuario_id: int
    usuario_nome: str | None = None
    texto: str | None = None
    resposta_a_id: int | None = None
    excluido: bool
    criado_em: datetime
    editado_em: datetime | None = None


# --------------------------------------------------------- Fase 2: atividade


class AtividadeOut(ORMModel):
    id: int
    cartao_id: int
    usuario_id: int | None = None
    usuario_nome: str | None = None
    tipo: str
    dados: dict | None = None
    criado_em: datetime


def _validar_cor(valor: str) -> str:
    """Aceita `#RRGGBB` ou `#AARRGGBB` (preferência de daltonismo usa alfa)."""
    texto = (valor or "").strip().upper()
    if not texto.startswith("#"):
        texto = f"#{texto}"
    hexa = texto[1:]
    if len(hexa) not in (6, 8) or any(c not in "0123456789ABCDEF" for c in hexa):
        raise ValueError("Cor inválida; use #RRGGBB.")
    return texto


CartaoOut.model_rebuild()
