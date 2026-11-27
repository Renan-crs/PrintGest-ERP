"""Serviço da Venda de Balcão (PDV) — PRD v2.0 §2.1/§2.2, roadmap item 7.

Regra central (PRD §2.2 "baixa automática de estoque via `movimento_estoque`"):
ao confirmar uma venda de balcão, o sistema decrementa o saldo de cada produto
controlado por estoque na filial e registra o kardex (SAIDA / origem
`venda_balcao`) na MESMA transação. O cancelamento estorna (ENTRADA) devolvendo o
saldo. Valores sempre `Decimal`. Nível mínimo exigido: CAIXA (PRD §5 RBAC —
caixa PODE venda de balcão, ao contrário da OS).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy import String, cast, or_, text as sa_text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.cadastros import Cliente, MovimentoEstoque, Produto, ProdutoEstoque
from app.models.enums import (
    FormaPagamento,
    OrigemMov,
    StatusCaixa,
    StatusVenda,
    TipoMovCaixa,
    TipoMovEstoque,
)
from app.models.financeiro import Caixa, MovimentoCaixa
from app.models.movimento import VendaBalcao, VendaBalcaoItem, VendaPagamento
from app.schemas.venda import (
    PagamentoVendaIn,
    PagamentoVendaOut,
    VendaCreate,
    VendaItemIn,
    VendaItemOut,
    VendaOut,
)
from app.services import adiantamento_service, custo_service, filial_service
from app.services.precificacao_documento import (
    gerar_snapshot,
    resolver_preco_linha,
    resolver_regras_dos_itens,
)
from app.services.regra_preco_service import RegraResolvida

_TWO = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_TWO, rounding=ROUND_HALF_UP)


def _erro_integridade() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Dados inválidos: referência inexistente ou violação de unicidade.",
    )


def _montar_item(
    payload: VendaItemIn, seq: int, resolvida: RegraResolvida | None = None
) -> VendaBalcaoItem:
    # A regra persistida no servidor é soberana; a do payload só é usada quando
    # não há regra vigente (simulação/compatibilidade).
    regra = resolvida.regra if resolvida else payload.regra_preco
    unitario, total, explicacao = resolver_preco_linha(
        valor_unitario=payload.valor_unitario,
        quantidade=payload.quantidade,
        desconto=payload.desconto,
        regra=regra,
    )
    item = VendaBalcaoItem(
        seq=seq,
        produto_id=payload.produto_id,
        descricao_avulsa=payload.descricao_avulsa,
        quantidade=payload.quantidade,
        valor_unitario=unitario,
        desconto=payload.desconto,
        valor_total=total,
    )
    # Transiente: devolvido na resposta (guia RF-VR-14 em V0).
    item._explicacao = explicacao
    if resolvida is not None:
        item.preco_snapshot = gerar_snapshot(
            origem=resolvida.origem,
            regra_id=resolvida.regra_id,
            tabela_id=resolvida.tabela_id,
            unitario=unitario,
            total=total,
            desconto=payload.desconto,
            explicacao=explicacao,
            vigencia_inicio=resolvida.vigencia_inicio,
            vigencia_fim=resolvida.vigencia_fim,
        )
    return item


def _montar_itens(
    itens: list[VendaItemIn], resolvidas: list[RegraResolvida | None] | None = None
) -> list[VendaBalcaoItem]:
    resolvidas = resolvidas or [None] * len(itens)
    montados: list[VendaBalcaoItem] = []
    for indice, item in enumerate(itens):
        montados.append(_montar_item(item, indice + 1, resolvidas[indice]))
    return montados


def _totais(itens: list[VendaBalcaoItem], desconto: Decimal) -> tuple[Decimal, Decimal]:
    valor_itens = _q(sum((i.valor_total for i in itens), Decimal(0)))
    if desconto > valor_itens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O desconto não pode ser maior que o valor dos itens.",
        )
    return valor_itens, _q(valor_itens - desconto)


def _para_out(venda: VendaBalcao) -> VendaOut:
    dados = {c.name: getattr(venda, c.name) for c in venda.__table__.columns}
    nome_avulso = (getattr(venda, "cliente_nome_avulso", None) or "").strip() or None
    dados["cliente_nome"] = venda.cliente.nome_razao if venda.cliente else nome_avulso
    dados["cliente_nome_avulso"] = nome_avulso
    dados["vendedor_nome"] = venda.vendedor.nome if venda.vendedor else None
    dados["operador_caixa_nome"] = venda.operador.nome if venda.operador else None
    dados["itens"] = [
        VendaItemOut(
            id=i.id,
            seq=i.seq,
            produto_id=i.produto_id,
            descricao_avulsa=i.descricao_avulsa,
            quantidade=i.quantidade,
            valor_unitario=i.valor_unitario,
            desconto=i.desconto,
            valor_total=i.valor_total,
            explicacao=getattr(i, "_explicacao", []),
            regra_aplicada=i.preco_snapshot,
        )
        for i in venda.itens
    ]
    dados["pagamentos"] = [
        PagamentoVendaOut.model_validate(p) for p in (venda.pagamentos or [])
    ]
    return VendaOut.model_validate(dados)


def _baixar_estoque(
    db: Session,
    *,
    filial_id: int,
    venda: VendaBalcao,
    usuario_id: int | None,
) -> None:
    """Registra o kardex (SAIDA/ENTRADA) e atualiza o saldo de cada item."""
    for item in venda.itens:
        if item.produto_id is None:
            continue  # item avulso não movimenta estoque
        produto = db.get(Produto, item.produto_id)
        if produto is None or not produto.controla_estoque:
            continue

        est = (
            db.query(ProdutoEstoque)
            .filter(
                ProdutoEstoque.filial_id == filial_id,
                ProdutoEstoque.produto_id == item.produto_id,
            )
            .first()
        )
        if est is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Produto sem posição de estoque nesta filial. "
                    "Cadastre o estoque antes de vender."
                ),
            )
        anterior = Decimal(est.saldo)
        if venda.status == StatusVenda.OK:
            # Baixa otimista e atômica: UPDATE ... WHERE saldo >= qtd.
            # Se outra estação já consumiu o saldo, rowcount=0 → 409.
            # Nunca produce saldo negativo sob concorrência (PRD §6).
            resultado = db.execute(
                sa_text(
                    "UPDATE produto_estoque SET saldo = saldo - :qtd, "
                    "atualizado_em = now() "
                    "WHERE filial_id = :filial AND produto_id = :produto "
                    "AND saldo >= :qtd"
                ),
                {
                    "qtd": item.quantidade,
                    "filial": filial_id,
                    "produto": item.produto_id,
                },
            )
            if resultado.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Estoque insuficiente para '{produto.nome}'. "
                        "Outra venda pode ter baixado o saldo agora. "
                        "Consulte o estoque e tente novamente."
                    ),
                )
            db.expire(est)
            saldo_final = Decimal(
                db.execute(
                    sa_text(
                        "SELECT saldo FROM produto_estoque "
                        "WHERE filial_id = :filial AND produto_id = :produto"
                    ),
                    {"filial": filial_id, "produto": item.produto_id},
                ).scalar_one()
            )
            est.saldo = saldo_final
            tipo = TipoMovEstoque.SAIDA
        else:  # estorno por cancelamento
            db.execute(
                sa_text(
                    "UPDATE produto_estoque SET saldo = saldo + :qtd, "
                    "atualizado_em = now() "
                    "WHERE filial_id = :filial AND produto_id = :produto"
                ),
                {
                    "qtd": item.quantidade,
                    "filial": filial_id,
                    "produto": item.produto_id,
                },
            )
            db.expire(est)
            saldo_final = Decimal(
                db.execute(
                    sa_text(
                        "SELECT saldo FROM produto_estoque "
                        "WHERE filial_id = :filial AND produto_id = :produto"
                    ),
                    {"filial": filial_id, "produto": item.produto_id},
                ).scalar_one()
            )
            est.saldo = saldo_final
            tipo = TipoMovEstoque.ENTRADA

        db.add(
            MovimentoEstoque(
                filial_id=filial_id,
                produto_id=item.produto_id,
                tipo=tipo,
                origem=OrigemMov.VENDA_BALCAO,
                documento_id=venda.id,
                # Convenção do kardex: ENTRADA positiva, SAIDA negativa.
                quantidade=(
                    -item.quantidade if tipo == TipoMovEstoque.SAIDA
                    else item.quantidade
                ),
                saldo_anterior=anterior,
                saldo_posterior=est.saldo,
                motivo="Venda de balcão"
                if venda.status == StatusVenda.OK
                else "Estorno por cancelamento de venda de balcão",
                usuario_id=usuario_id,
            )
        )


def _registrar_no_caixa(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    venda: VendaBalcao,
    valor: Decimal | None = None,
    forma: FormaPagamento | None = None,
) -> None:
    """Lança no caixa o valor **efetivamente recebido** nesta venda.

    FIADO não entra no caixa (a conta fica a receber). Quando existe
    sinal/adiantamento, esse valor já entrou como movimento próprio — aqui
    entra apenas a diferença, para não contar o mesmo dinheiro duas vezes.
    """
    entrada = _q(valor if valor is not None else venda.valor_total)
    forma_efetiva = forma or venda.forma_pagamento
    if forma_efetiva == FormaPagamento.FIADO:
        return
    caixa = (
        db.query(Caixa)
        .filter(
            Caixa.filial_id == filial_id,
            Caixa.usuario_id == usuario_id,
            Caixa.status == StatusCaixa.ABERTO,
        )
        .first()
    )
    if caixa is None:
        return  # a rota já exige caixa aberto; resguardo para chamadas internas
    venda.caixa_id = caixa.id
    if entrada <= 0:
        return  # 100% adiantado: o único movimento é o do sinal
    db.add(
        MovimentoCaixa(
            caixa_id=caixa.id,
            tipo=TipoMovCaixa.ENTRADA,
            venda_balcao_id=venda.id,
            descricao=f"Venda de balcão Nº {venda.numero} "
            f"({FormaPagamento(forma_efetiva).value})",
            valor=entrada,
            usuario_id=usuario_id,
        )
    )


def _validar_pagamentos(
    dados: VendaCreate, valor_total: Decimal
) -> list[PagamentoVendaIn]:
    """Split payment: a soma das formas deve fechar exatamente com o total."""
    if not dados.pagamentos:
        return []
    if len(dados.pagamentos) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Máximo de 10 formas de pagamento por venda.",
        )
    soma = sum((_q(p.valor) for p in dados.pagamentos), Decimal("0.00"))
    if abs(soma - valor_total) > Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"A soma das formas de pagamento ({soma}) deve igualar o total "
                f"da venda ({valor_total})."
            ),
        )
    return list(dados.pagamentos)


def criar(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    dados: VendaCreate,
) -> VendaOut:
    resolvidas = resolver_regras_dos_itens(
        db,
        filial_id=filial_id,
        cliente_id=dados.cliente_id,
        itens=dados.itens,
    )
    itens = _montar_itens(dados.itens, resolvidas)
    # V2: custo/margem entram no snapshot quando há ficha de consumo vigente.
    for item, resolvida in zip(itens, resolvidas):
        if resolvida is None or item.preco_snapshot is None:
            continue
        custo, margem = custo_service.custo_e_margem(
            db,
            filial_id=filial_id,
            produto_id=item.produto_id,
            preco_unitario=item.valor_unitario,
        )
        if custo is not None:
            item.preco_snapshot["custo_unitario"] = str(custo)
            item.preco_snapshot["margem_bruta"] = (
                str(margem) if margem is not None else None
            )
    valor_itens, valor_total = _totais(itens, dados.desconto)
    pagamentos = _validar_pagamentos(dados, valor_total)
    principal = pagamentos[0] if pagamentos else None
    forma_efetiva = principal.forma_pagamento if principal else dados.forma_pagamento
    parcelas_efetivas = principal.parcelas if principal else dados.parcelas
    recebido_informado = (
        principal.valor_recebido if principal else dados.valor_recebido
    )
    troco_informado = principal.troco if principal else dados.troco
    valor_principal = (
        valor_total - sum((_q(p.valor) for p in pagamentos[1:]), Decimal("0.00"))
        if pagamentos else valor_total
    )

    cliente_nome_avulso = (dados.cliente_nome_avulso or "").strip() or None
    if dados.cliente_id:
        cliente_nome_avulso = None

    valor_recebido = None
    troco = None
    if recebido_informado is not None:
        valor_recebido = _q(recebido_informado)
    if forma_efetiva == FormaPagamento.DINHEIRO and valor_recebido is not None:
        troco_calc = valor_recebido - valor_principal
        troco = _q(troco_calc) if troco_calc > 0 else Decimal("0.00")
    elif troco_informado is not None:
        troco = _q(troco_informado)

    venda = VendaBalcao(
        filial_id=filial_id,
        status=StatusVenda.OK,
        cliente_id=dados.cliente_id,
        cliente_nome_avulso=cliente_nome_avulso,
        vendedor_id=dados.vendedor_id,
        operador_caixa=usuario_id,
        data_venda=dados.data_venda,
        valor_itens=valor_itens,
        desconto=dados.desconto,
        valor_total=valor_total,
        forma_pagamento=forma_efetiva,
        parcelas=parcelas_efetivas,
        valor_recebido=valor_recebido,
        troco=troco,
        observacoes=dados.observacoes,
        itens=itens,
        pagamentos=[
            VendaPagamento(
                seq=indice,
                forma_pagamento=p.forma_pagamento,
                valor=_q(p.valor),
                parcelas=p.parcelas,
                valor_recebido=(
                    _q(p.valor_recebido) if p.valor_recebido is not None else None
                ),
                troco=_q(p.troco) if p.troco is not None else None,
            )
            for indice, p in enumerate(pagamentos, start=1)
        ],
    )
    db.add(venda)
    try:
        db.flush()  # garante venda.id para o kardex antes do commit
        adiantamento = None
        if dados.cliente_id:
            cliente = db.get(Cliente, dados.cliente_id)
            adiantamento = adiantamento_service.exigir_e_registrar(
                db,
                filial_id=filial_id,
                usuario_id=usuario_id,
                cliente=cliente,
                valor_total=valor_total,
                confirmado=dados.pagamento_confirmado,
                documento=f"Venda #{venda.id}",
                venda_balcao_id=venda.id,
            )

        # Valor que realmente entrou agora (sinal já tem movimento próprio).
        recebido_agora = valor_total - (adiantamento.valor if adiantamento else Decimal(0))
        if recebido_agora < 0:
            recebido_agora = Decimal("0.00")

        # FIADO e boleto parcelado: o restante fica como título a receber.
        # Cartão/dinheiro recebem o valor na hora; parcelas são com o operador.
        _baixar_estoque(db, filial_id=filial_id, venda=venda, usuario_id=usuario_id)

        if pagamentos:
            # Split: cada forma gera seu próprio movimento. FIADO/BOLETO viram
            # título a receber; as demais entram no caixa até o adiantamento.
            restante = recebido_agora
            for pagamento in pagamentos:
                if pagamento.forma_pagamento in (
                    FormaPagamento.FIADO, FormaPagamento.BOLETO
                ):
                    adiantamento_service.registrar_saldo_devedor(
                        db,
                        filial_id=filial_id,
                        cliente_id=dados.cliente_id,
                        valor=_q(pagamento.valor),
                        documento=f"Venda #{venda.numero or venda.id}",
                        venda_balcao_id=venda.id,
                        parcelas=(
                            pagamento.parcelas
                            if pagamento.forma_pagamento == FormaPagamento.BOLETO
                            else 1
                        ),
                    )
                    continue
                valor_caixa = min(_q(pagamento.valor), restante)
                restante -= valor_caixa
                _registrar_no_caixa(
                    db, filial_id=filial_id, usuario_id=usuario_id, venda=venda,
                    valor=valor_caixa, forma=pagamento.forma_pagamento,
                )
        else:
            if forma_efetiva in (FormaPagamento.FIADO, FormaPagamento.BOLETO):
                adiantamento_service.registrar_saldo_devedor(
                    db,
                    filial_id=filial_id,
                    cliente_id=dados.cliente_id,
                    valor=recebido_agora,
                    documento=f"Venda #{venda.numero or venda.id}",
                    venda_balcao_id=venda.id,
                    parcelas=parcelas_efetivas if forma_efetiva == FormaPagamento.BOLETO else 1,
                )
                recebido_agora = Decimal("0.00")
            _registrar_no_caixa(
                db, filial_id=filial_id, usuario_id=usuario_id, venda=venda,
                valor=recebido_agora,
            )
        # PRD v3.3 RF-SY-01: evento de sync na MESMA transação da venda.
        filial_service.registrar_evento(
            db,
            filial_id=filial_id,
            entidade="venda_balcao",
            entidade_id=venda.id,
            operacao="CRS",
            payload={
                "numero": venda.numero,
                "valor_total": str(venda.valor_total),
                "forma_pagamento": str(venda.forma_pagamento.value),
                "data_venda": venda.data_venda.isoformat() if venda.data_venda else None,
            },
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(venda)
    return _para_out(venda)


def buscar(db: Session, venda_id: int, *, filial_id: int) -> VendaBalcao:
    venda = (
        db.query(VendaBalcao)
        .options(
            joinedload(VendaBalcao.cliente),
            joinedload(VendaBalcao.vendedor),
            joinedload(VendaBalcao.operador),
            selectinload(VendaBalcao.itens),
            selectinload(VendaBalcao.pagamentos),
        )
        .filter(VendaBalcao.id == venda_id, VendaBalcao.filial_id == filial_id)
        .first()
    )
    if not venda:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venda de balcão não encontrada.",
        )
    return venda


def listar(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    status_venda: StatusVenda | None = None,
    forma_pagamento: FormaPagamento | None = None,
    operador_id: int | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[VendaOut], int]:
    base = db.query(VendaBalcao).filter(VendaBalcao.filial_id == filial_id)
    if status_venda:
        base = base.filter(VendaBalcao.status == status_venda)
    if forma_pagamento:
        base = base.filter(VendaBalcao.forma_pagamento == forma_pagamento)
    if operador_id:
        base = base.filter(VendaBalcao.operador_caixa == operador_id)
    if data_inicio:
        base = base.filter(VendaBalcao.data_venda >= data_inicio)
    if data_fim:
        base = base.filter(VendaBalcao.data_venda <= data_fim)
    if q:
        termo = f"%{q.strip()}%"
        base = base.outerjoin(Cliente, VendaBalcao.cliente_id == Cliente.id).filter(
            or_(
                Cliente.nome_razao.ilike(termo),
                cast(VendaBalcao.numero, String).ilike(termo),
            )
        )
    total = base.count()
    itens = (
        base.options(
            joinedload(VendaBalcao.cliente),
            joinedload(VendaBalcao.vendedor),
            joinedload(VendaBalcao.operador),
            selectinload(VendaBalcao.itens),
            selectinload(VendaBalcao.pagamentos),
        )
        .order_by(VendaBalcao.numero.desc())
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
        .all()
    )
    return [_para_out(v) for v in itens], total


def cancelar(
    db: Session,
    *,
    filial_id: int,
    venda_id: int,
    usuario_id: int | None = None,
    motivo: str | None = None,
) -> None:
    from datetime import datetime, timezone

    venda = buscar(db, venda_id, filial_id=filial_id)
    if venda.status == StatusVenda.CANCELADO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Venda de balcão já cancelada.",
        )
    venda.status = StatusVenda.CANCELADO
    venda.motivo_cancelamento = (motivo or "").strip() or None
    venda.cancelado_em = datetime.now(timezone.utc)
    venda.cancelado_por = usuario_id
    _baixar_estoque(db, filial_id=filial_id, venda=venda, usuario_id=usuario_id)
    _estornar_caixa(db, venda=venda, filial_id=filial_id)
    filial_service.registrar_evento(
        db,
        filial_id=filial_id,
        entidade="venda_balcao",
        entidade_id=venda.id,
        operacao="UPD",
        payload={
            "status": str(venda.status.value),
            "motivo_cancelamento": venda.motivo_cancelamento,
        },
    )
    db.commit()


def resumo(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    status_venda: StatusVenda | None = None,
    forma_pagamento: FormaPagamento | None = None,
    operador_id: int | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict:
    base = db.query(VendaBalcao).filter(VendaBalcao.filial_id == filial_id)
    if status_venda:
        base = base.filter(VendaBalcao.status == status_venda)
    if forma_pagamento:
        base = base.filter(VendaBalcao.forma_pagamento == forma_pagamento)
    if operador_id:
        base = base.filter(VendaBalcao.operador_caixa == operador_id)
    if data_inicio:
        base = base.filter(VendaBalcao.data_venda >= data_inicio)
    if data_fim:
        base = base.filter(VendaBalcao.data_venda <= data_fim)
    if q:
        termo = f"%{q.strip()}%"
        base = base.outerjoin(Cliente, VendaBalcao.cliente_id == Cliente.id).filter(
            or_(
                Cliente.nome_razao.ilike(termo),
                cast(VendaBalcao.numero, String).ilike(termo),
            )
        )
    from sqlalchemy import func as sa_func

    total = base.with_entities(sa_func.coalesce(sa_func.sum(VendaBalcao.valor_total), 0)).scalar()
    quantidade = base.with_entities(sa_func.count(VendaBalcao.id)).scalar() or 0
    linhas = (
        base.with_entities(
            VendaBalcao.forma_pagamento,
            sa_func.count(VendaBalcao.id),
            sa_func.coalesce(sa_func.sum(VendaBalcao.valor_total), 0),
        )
        .group_by(VendaBalcao.forma_pagamento)
        .all()
    )
    por_forma = [
        {
            "forma_pagamento": str(fp.value if hasattr(fp, "value") else fp),
            "quantidade": int(qtd or 0),
            "total": tot or 0,
        }
        for fp, qtd, tot in linhas
    ]
    return {"quantidade": int(quantidade), "total": total or 0, "por_forma": por_forma}


def _estornar_caixa(db: Session, *, venda: VendaBalcao, filial_id: int) -> None:
    """Estorna a entrada da venda cancelada no caixa (se ainda estiver aberto).

    Se o caixa da venda já foi fechado, não há como alterar o fechamento — o
    ajuste fica na conferência (o operador lança sangria) ou no próximo caixa.
    """
    if venda.caixa_id is None or venda.valor_total <= 0:
        return
    caixa = db.get(Caixa, venda.caixa_id)
    if caixa is None or caixa.status != StatusCaixa.ABERTO:
        return
    if venda.forma_pagamento == FormaPagamento.FIADO:
        return
    db.add(
        MovimentoCaixa(
            caixa_id=caixa.id,
            tipo=TipoMovCaixa.SAIDA,
            venda_balcao_id=venda.id,
            descricao=f"Estorno — venda de balcão Nº {venda.numero} cancelada",
            valor=_q(venda.valor_total),
            usuario_id=None,
        )
    )
