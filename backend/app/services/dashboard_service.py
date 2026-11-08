"""Serviço do Dashboard — agregações reais da Tela Inicial.

Recupera, para a filial do usuário:
  - Vendas de balcão do dia (quantidade e valor) e do dia anterior — status `ok`.
  - O.S. abertas/prontas e projetos (O.S. tipo `os` em produção e atrasadas).
  - Para níveis operacionais (>= OPERADOR): itens de estoque abaixo do mínimo
    (reutilizando `estoque_service.resumo`) e as entregas do dia (O.S. com
    prazo <= hoje).
  - Para níveis gerenciais (>= GERENTE): a receber (vence hoje / atrasado,
    saldo em aberto de `conta_receber`), o faturamento previsto (contas a
    receber com vencimento no período) e a série de vendas dos últimos `dias`
    dias (dias sem movimento entram zerados — sem inventar números).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.deps import RANK
from app.models.core import Filial
from app.models.enums import (
    NivelAcesso,
    StatusConta,
    StatusOs,
    StatusVenda,
    TipoOs,
)
from app.models.financeiro import ContaReceber
from app.models.movimento import OrdemServico, VendaBalcao
from app.schemas.dashboard import (
    DashboardEntregaOut,
    DashboardResumoOut,
    DashboardVendaDiaOut,
)
from app.services import estoque_service

_NAO_ENTREGUE = (StatusOs.ENTREGUE, StatusOs.CANCELADO, StatusOs.CONVERTIDO)


def _money(v: Decimal) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _contar_os(db: Session, filial_id: int, status: StatusOs) -> int:
    return (
        db.query(func.count(OrdemServico.id))
        .filter(
            OrdemServico.filial_id == filial_id,
            OrdemServico.tipo == TipoOs.OS,
            OrdemServico.status == status,
        )
        .scalar()
        or 0
    )


def _contar_os_atrasadas(db: Session, filial_id: int, hoje: date) -> int:
    return (
        db.query(func.count(OrdemServico.id))
        .filter(
            OrdemServico.filial_id == filial_id,
            OrdemServico.tipo == TipoOs.OS,
            OrdemServico.data_previsao_entrega.is_not(None),
            OrdemServico.data_previsao_entrega < hoje,
            OrdemServico.status.not_in(_NAO_ENTREGUE),
        )
        .scalar()
        or 0
    )


def _vendas_no_dia(db: Session, filial_id: int, dia: date) -> tuple[int, Decimal]:
    qtd, valor = (
        db.query(
            func.count(VendaBalcao.id),
            func.coalesce(func.sum(VendaBalcao.valor_total), 0),
        )
        .filter(
            VendaBalcao.filial_id == filial_id,
            VendaBalcao.status == StatusVenda.OK,
            VendaBalcao.data_venda == dia,
        )
        .one()
    )
    return int(qtd or 0), _money(valor)


def _vendas_ultimos_dias(
    db: Session, filial_id: int, hoje: date, dias: int = 7
) -> list[DashboardVendaDiaOut]:
    inicio = hoje - timedelta(days=dias - 1)
    por_dia: dict[date, Decimal] = {}
    for data_venda, valor in (
        db.query(
            VendaBalcao.data_venda,
            func.coalesce(func.sum(VendaBalcao.valor_total), 0),
        )
        .filter(
            VendaBalcao.filial_id == filial_id,
            VendaBalcao.status == StatusVenda.OK,
            VendaBalcao.data_venda >= inicio,
            VendaBalcao.data_venda <= hoje,
        )
        .group_by(VendaBalcao.data_venda)
        .all()
    ):
        por_dia[data_venda] = valor
    serie: list[DashboardVendaDiaOut] = []
    for i in range(dias):
        dia = inicio + timedelta(days=i)
        serie.append(DashboardVendaDiaOut(data=dia, valor=_money(por_dia.get(dia, 0))))
    return serie


def _somar_saldo_receber(
    db: Session,
    filial_id: int,
    *,
    antes_de: date | None = None,
    no_dia: date | None = None,
) -> Decimal:
    """Saldo em aberto (valor − pago) das contas a receber ativas.

    Filtra por `vencimento == no_dia` (vence hoje) ou `vencimento < antes_de`
    (atrasado). Sem filtro, soma todo o saldo em aberto da filial.
    """
    filtros = [
        ContaReceber.filial_id == filial_id,
        ContaReceber.status == StatusConta.ABERTA,
    ]
    if no_dia is not None:
        filtros.append(ContaReceber.vencimento == no_dia)
    elif antes_de is not None:
        filtros.append(ContaReceber.vencimento < antes_de)
    saldo = (
        db.query(
            func.coalesce(
                func.sum(
                    ContaReceber.valor - func.coalesce(ContaReceber.valor_pago, 0)
                ),
                0,
            )
        )
        .filter(*filtros)
        .scalar()
        or 0
    )
    return _money(saldo)


def _previsto_por_dia(
    db: Session, filial_id: int, hoje: date, dias: int
) -> list[DashboardVendaDiaOut]:
    fim = hoje + timedelta(days=dias - 1)
    por_dia: dict[date, Decimal] = {}
    for vencimento, valor in (
        db.query(
            ContaReceber.vencimento,
            func.coalesce(
                func.sum(
                    ContaReceber.valor - func.coalesce(ContaReceber.valor_pago, 0)
                ),
                0,
            ),
        )
        .filter(
            ContaReceber.filial_id == filial_id,
            ContaReceber.status == StatusConta.ABERTA,
            ContaReceber.vencimento >= hoje,
            ContaReceber.vencimento <= fim,
        )
        .group_by(ContaReceber.vencimento)
        .all()
    ):
        por_dia[vencimento] = valor
    serie: list[DashboardVendaDiaOut] = []
    for i in range(dias):
        dia = hoje + timedelta(days=i)
        serie.append(DashboardVendaDiaOut(data=dia, valor=_money(por_dia.get(dia, 0))))
    return serie


def _entregas_do_dia(
    db: Session, filial_id: int, hoje: date, limite: int = 15
) -> list[DashboardEntregaOut]:
    abertas = (
        db.query(OrdemServico)
        .options(joinedload(OrdemServico.cliente), selectinload(OrdemServico.itens))
        .filter(
            OrdemServico.filial_id == filial_id,
            OrdemServico.tipo == TipoOs.OS,
            OrdemServico.data_previsao_entrega.is_not(None),
            OrdemServico.data_previsao_entrega <= hoje,
            OrdemServico.status.not_in(_NAO_ENTREGUE),
        )
        .order_by(OrdemServico.data_previsao_entrega.asc())
        .limit(limite)
        .all()
    )
    entregas: list[DashboardEntregaOut] = []
    for os_ in abertas:
        primeiro_item = os_.itens[0] if os_.itens else None
        entregas.append(
            DashboardEntregaOut(
                os_id=os_.id,
                numero=os_.numero,
                cliente_nome=os_.cliente.nome_razao if os_.cliente else None,
                servico=primeiro_item.descricao_avulsa if primeiro_item else None,
                prazo=os_.data_previsao_entrega,
                status=os_.status.value,
                atrasada=os_.data_previsao_entrega < hoje,
            )
        )
    return entregas


def resumo(
    db: Session, *, filial_id: int, nivel: NivelAcesso, dias: int = 7
) -> DashboardResumoOut:
    filial = db.get(Filial, filial_id)
    hoje = date.today()
    ontem = hoje - timedelta(days=1)

    vendas_hoje_qtd, vendas_hoje_valor = _vendas_no_dia(db, filial_id, hoje)
    vendas_ontem_qtd, vendas_ontem_valor = _vendas_no_dia(db, filial_id, ontem)

    operacional = RANK.get(nivel, 0) >= RANK[NivelAcesso.OPERADOR]
    gerencial = RANK.get(nivel, 0) >= RANK[NivelAcesso.GERENTE]

    return DashboardResumoOut(
        filial_nome=filial.nome if filial else None,
        vendas_hoje_qtd=vendas_hoje_qtd,
        vendas_hoje_valor=vendas_hoje_valor,
        vendas_ontem_qtd=vendas_ontem_qtd,
        vendas_ontem_valor=vendas_ontem_valor,
        os_abertas=_contar_os(db, filial_id, StatusOs.ABERTO),
        os_prontas=_contar_os(db, filial_id, StatusOs.PRONTA),
        # operacional (>= OPERADOR)
        projetos_em_producao=_contar_os(db, filial_id, StatusOs.PRODUCAO)
        if operacional
        else None,
        projetos_atrasados=_contar_os_atrasadas(db, filial_id, hoje)
        if operacional
        else None,
        estoque_abaixo_minimo=(
            estoque_service.resumo(db, filial_id).abaixo_minimo if operacional else None
        ),
        entregas_hoje=_entregas_do_dia(db, filial_id, hoje) if operacional else None,
        # gerencial (>= GERENTE)
        a_receber_vence_hoje=_somar_saldo_receber(db, filial_id, no_dia=hoje)
        if gerencial
        else None,
        a_receber_atrasado=_somar_saldo_receber(db, filial_id, antes_de=hoje)
        if gerencial
        else None,
        faturamento_previsto=_previsto_por_dia(db, filial_id, hoje, dias)
        if gerencial
        else None,
        vendas_7_dias=_vendas_ultimos_dias(db, filial_id, hoje, dias)
        if gerencial
        else None,
    )
