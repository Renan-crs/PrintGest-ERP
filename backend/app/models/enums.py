from enum import StrEnum
import re

from sqlalchemy import Enum as SAEnum


def _enum_type_name(enum_cls: type[StrEnum]) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", enum_cls.__name__).lower()


def pg_enum(enum_cls: type[StrEnum]) -> SAEnum:
    """SQLAlchemy Enum que persiste os *valores* (minúsculas, ex.: 'admin').

    Alinha a nomenclatura dos tipos PostgreSQL com o schema.sql de referência.
    """
    return SAEnum(
        enum_cls,
        name=_enum_type_name(enum_cls),
        values_callable=lambda c: [v.value for v in c],
    )


class NivelAcesso(StrEnum):
    ADMIN = "admin"
    GERENTE = "gerente"
    OPERADOR = "operador"
    CAIXA = "caixa"


class TipoPessoa(StrEnum):
    PF = "pf"
    PJ = "pj"


class TipoProduto(StrEnum):
    PRODUTO = "produto"
    SERVICO = "servico"


class TipoMovEstoque(StrEnum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    AJUSTE = "ajuste"


class OrigemMov(StrEnum):
    VENDA_BALCAO = "venda_balcao"
    ORDEM_SERVICO = "ordem_servico"
    PEDIDO_COMPRA = "pedido_compra"
    AJUSTE_MANUAL = "ajuste_manual"


class TipoOs(StrEnum):
    ORCAMENTO = "orcamento"
    OS = "os"


class TipoItemOs(StrEnum):
    """M1 (PRD v3.0 §3.2.2): item próprio é produzido internamente; item de
    fornecedor é terceirizado — entra como "Aguardando cotação" até alguém
    com permissão lançar a cotação que define o valor (VO)."""

    PROPRIO = "proprio"
    FORNECEDOR = "fornecedor"


class ConferenciaTerceirizado(StrEnum):
    """M4 (PRD v3.0 §3.6): conferência de qualidade do item terceirizado."""

    PENDENTE = "pendente"
    OK = "ok"
    REFACAO = "refacao"


class DecisaoArte(StrEnum):
    """M3 (PRD v3.0 §3.5): decisão do cliente sobre a prova da arte."""

    APROVADA = "aprovada"
    AJUSTE = "ajuste"


class TipoLinkPublico(StrEnum):
    """M3 (PRD v3.0 §3.5): para que serve o link público."""

    PROVA = "prova"
    ORCAMENTO = "orcamento"


class RefacaoErro(StrEnum):
    """M3 (PRD v3.0 §3.10): de quem foi o erro na refação."""

    GRAFICA = "grafica"
    CLIENTE = "cliente"


class StatusOs(StrEnum):
    ABERTO = "aberto"
    AGUARDANDO_ARTE = "aguardando_arte"  # M3 (§3.5): aguardando arte do cliente
    AGUARDANDO_APROVACAO = (
        "aguardando_aprovacao"  # M3 (§3.5): prova enviada, aguardando decisão
    )
    APROVADO = "aprovado"
    PRODUCAO = "producao"
    PRONTA = "pronta"
    ENTREGUE = "entregue"
    CANCELADO = "cancelado"
    CONVERTIDO = "convertido"


class StatusVenda(StrEnum):
    OK = "ok"
    CANCELADO = "cancelado"


class StatusPedido(StrEnum):
    ABERTO = "aberto"
    RECEBIDO = "recebido"
    CANCELADO = "cancelado"


class StatusAgenda(StrEnum):
    AGENDADO = "agendado"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"


class TipoAgenda(StrEnum):
    PRODUCAO = "producao"
    ENTREGA = "entrega"


class TipoLista(StrEnum):
    """Tipos de lista do quadro de Projetos (PRD Módulo Projetos §4.1).

    O `tipo` define o papel da lista no fluxo e, quando acompanhado de
    `status_os`, sincroniza o cartão vinculado com a O.S. (RN2). `livre` não
    altera a O.S.; `usuario` é a lista pessoal de um membro (PV3).
    """

    ORCAMENTO = "orcamento"
    USUARIO = "usuario"
    APROVACAO = "aprovacao"
    PRODUCAO = "producao"
    TERCEIRO = "terceiro"
    FINAL = "final"
    LIVRE = "livre"


class OrigemMembro(StrEnum):
    """Por que um usuário virou membro do cartão (PRD Módulo Projetos §9/PV3)."""

    MANUAL = "manual"
    LISTA = "lista"
    ATRIBUIDOR = "atribuidor"


class TipoPlanoConta(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"


class StatusConta(StrEnum):
    ABERTA = "aberta"
    PAGA = "paga"
    CANCELADA = "cancelada"


class StatusCaixa(StrEnum):
    ABERTO = "aberto"
    FECHADO = "fechado"


class TipoMovCaixa(StrEnum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    SANGRIA = "sangria"
    SUPRIMENTO = "suprimento"


class FormaPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    CARTAO_CREDITO = "cartao_credito"
    CARTAO_DEBITO = "cartao_debito"
    PIX = "pix"
    BOLETO = "boleto"
    FIADO = "fiado"


class ModeloFiscal(StrEnum):
    NFE = "nfe"
    NFCE = "nfce"


class StatusFiscal(StrEnum):
    RASCUNHO = "rascunho"
    PROCESSANDO = "processando"
    AUTORIZADO = "autorizado"
    REJEITADO = "rejeitado"
    CANCELADO = "cancelado"
    CONTINGENCIADO = "contingenciado"