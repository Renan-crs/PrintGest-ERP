"""Serviços de Ordem de Serviço e Orçamento (PRD v2.0 §2.1, fluxo OS).

Regra central: orçamento e OS são registros de `ordem_servico` distinguidos por
`tipo`. A conversão de orçamento em OS cria um novo registro `os` com
`orcamento_origem_id` apontando para o orçamento e marca o original como
`convertido`. Todos os valores monetários são `Decimal` (nunca float).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.cadastros import Cliente, Produto
from app.models.enums import (
    DecisaoArte,
    RefacaoErro,
    StatusOs,
    StatusPedido,
    TipoItemOs,
    TipoOs,
)
from app.models.movimento import (
    ArteAprovacao,
    ArteVersao,
    OrdemServico,
    OrdemServicoItem,
    OrdemServicoItemCotacao,
    PedidoCompra,
    PedidoCompraItem,
)
from app.schemas.movimento import OsCreate, OsItemIn, OsItemOut, OsOut, OsUpdate
from app.services import adiantamento_service

_TWO = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_TWO, rounding=ROUND_HALF_UP)


def _erro_integridade() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Dados inválidos: referência inexistente ou violação de unicidade.",
    )


def _montar_item(payload: OsItemIn, seq: int) -> OrdemServicoItem:
    total = _q(payload.valor_unitario * payload.quantidade - payload.desconto)
    if total < 0:
        total = Decimal("0.00")
    return OrdemServicoItem(
        seq=seq,
        produto_id=payload.produto_id,
        descricao_avulsa=payload.descricao_avulsa,
        quantidade=payload.quantidade.quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        ),
        dimensoes=payload.dimensoes,
        valor_unitario=payload.valor_unitario,
        desconto=payload.desconto,
        valor_total=total,
        tipo=payload.tipo,
    )


def _montar_itens(itens: list[OsItemIn]) -> list[OrdemServicoItem]:
    return [_montar_item(item, seq) for seq, item in enumerate(itens, start=1)]


def _totais(
    itens: list[OrdemServicoItem], desconto: Decimal
) -> tuple[Decimal, Decimal]:
    valor_itens = _q(sum((i.valor_total for i in itens), Decimal(0)))
    if desconto > valor_itens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O desconto não pode ser maior que o valor dos itens.",
        )
    return valor_itens, _q(valor_itens - desconto)


def _para_out(os: OrdemServico) -> OsOut:
    dados = {c.name: getattr(os, c.name) for c in os.__table__.columns}
    dados["cliente_nome"] = os.cliente.nome_razao if os.cliente else None
    dados["vendedor_nome"] = os.vendedor.nome if os.vendedor else None
    dados["atendente_nome"] = os.atendente.nome if os.atendente else None
    itens_out = []
    for item in os.itens:
        saida = OsItemOut.model_validate(item)
        if item.tipo == TipoItemOs.FORNECEDOR:
            # Estado derivado (PRD §3.2.2): sem snapshot, o item está
            # "aguardando" (cotações ficam no orçamento — aqui o snapshot é a
            # prova de que foi cotado e selecionado).
            saida.estado_cotacao = "cotado" if item.snapshot_preco else "aguardando"
        itens_out.append(saida)
    dados["itens"] = itens_out
    return OsOut.model_validate(dados)


def buscar(db: Session, os_id: int, *, filial_id: int) -> OrdemServico:
    os_obj = (
        db.query(OrdemServico)
        .options(
            joinedload(OrdemServico.cliente),
            joinedload(OrdemServico.vendedor),
            joinedload(OrdemServico.atendente),
            selectinload(OrdemServico.itens),
            selectinload(OrdemServico.itens).selectinload(OrdemServicoItem.cotacoes),
        )
        .filter(OrdemServico.id == os_id, OrdemServico.filial_id == filial_id)
        .first()
    )
    if not os_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ordem de serviço não encontrada.",
        )
    return os_obj


def criar(db: Session, *, filial_id: int, usuario_id: int, dados: OsCreate) -> OsOut:
    itens = _montar_itens(dados.itens)
    valor_itens, valor_total = _totais(itens, dados.desconto)
    os_obj = OrdemServico(
        filial_id=filial_id,
        tipo=dados.tipo,
        status=StatusOs.ABERTO,
        cliente_id=dados.cliente_id,
        vendedor_id=dados.vendedor_id,
        atendente_id=dados.atendente_id,
        data_previsao_entrega=dados.data_previsao_entrega,
        desconto=dados.desconto,
        valor_itens=valor_itens,
        valor_total=valor_total,
        forma_pagamento=dados.forma_pagamento,
        observacoes=dados.observacoes,
        criado_por=usuario_id,
        itens=itens,
    )
    db.add(os_obj)
    try:
        db.flush()  # garante os_obj.id para o lançamento de adiantamento
        if dados.tipo == TipoOs.OS:
            cliente = db.get(Cliente, dados.cliente_id) if dados.cliente_id else None
            adiantamento_service.exigir_e_registrar(
                db,
                filial_id=filial_id,
                usuario_id=usuario_id,
                cliente=cliente,
                valor_total=valor_total,
                confirmado=dados.pagamento_confirmado,
                documento=f"O.S. #{os_obj.id}",
                ordem_servico_id=os_obj.id,
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(os_obj)
    return _para_out(os_obj)


def atualizar(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    dados: OsUpdate,
) -> OsOut:
    os_obj = buscar(db, os_id, filial_id=filial_id)
    if os_obj.status in (StatusOs.ENTREGUE, StatusOs.CANCELADO, StatusOs.CONVERTIDO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ordem de serviço {os_obj.status.value} não pode ser alterada.",
        )

    campos = dados.model_dump(exclude_unset=True)

    for campo in ("cliente_id", "vendedor_id", "atendente_id", "forma_pagamento"):
        if campo in campos:
            setattr(os_obj, campo, campos[campo])
    if "data_previsao_entrega" in campos:
        os_obj.data_previsao_entrega = dados.data_previsao_entrega
    if "observacoes" in campos:
        os_obj.observacoes = dados.observacoes

    desconto = dados.desconto if "desconto" in campos else os_obj.desconto
    if "itens" in campos:
        if dados.itens is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A lista de itens não pode ser nula.",
            )
        os_obj.itens = _montar_itens(dados.itens)
    valor_itens, valor_total = _totais(os_obj.itens, desconto)
    os_obj.desconto = desconto
    os_obj.valor_itens = valor_itens
    os_obj.valor_total = valor_total

    db.commit()
    db.refresh(os_obj)
    return _para_out(os_obj)


_TRANSICOES: dict[StatusOs, set[StatusOs]] = {
    StatusOs.ABERTO: {
        StatusOs.AGUARDANDO_ARTE,
        StatusOs.AGUARDANDO_APROVACAO,
        StatusOs.APROVADO,
        StatusOs.PRODUCAO,
        StatusOs.PRONTA,
        StatusOs.ENTREGUE,
        StatusOs.CANCELADO,
    },
    # M3 (§3.5): a arte chegou e aguarda o cliente decidir; o cancelamento
    # continua possível enquanto a produção não começou. PRODUCAO entra no
    # conjunto para o GATE responder (409 "sem arte aprovada") em vez de um
    # "transição inválida" menos instrutivo — produção só passa com arte
    # aprovada, e arte aprovada move o status para APROVADO antes.
    StatusOs.AGUARDANDO_ARTE: {
        StatusOs.AGUARDANDO_APROVACAO,
        StatusOs.PRODUCAO,
        StatusOs.CANCELADO,
    },
    StatusOs.AGUARDANDO_APROVACAO: {
        StatusOs.APROVADO,
        StatusOs.AGUARDANDO_ARTE,
        StatusOs.PRODUCAO,
        StatusOs.CANCELADO,
    },
    StatusOs.APROVADO: {
        StatusOs.PRODUCAO,
        StatusOs.PRONTA,
        StatusOs.ENTREGUE,
        StatusOs.CANCELADO,
    },
    StatusOs.PRODUCAO: {StatusOs.PRONTA, StatusOs.ENTREGUE, StatusOs.CANCELADO},
    StatusOs.PRONTA: {StatusOs.ENTREGUE, StatusOs.CANCELADO},
    StatusOs.ENTREGUE: set(),
    StatusOs.CANCELADO: set(),
    StatusOs.CONVERTIDO: set(),
}


def mudar_status(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    novo: StatusOs,
) -> OsOut:
    os_obj = buscar(db, os_id, filial_id=filial_id)

    if os_obj.tipo == TipoOs.ORCAMENTO:
        permitidos: set[StatusOs] = (
            {StatusOs.CANCELADO} if os_obj.status == StatusOs.ABERTO else set()
        )
    else:
        permitidos = _TRANSICOES.get(os_obj.status, set())

    if novo not in permitidos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Transição de status inválida: {os_obj.status.value} → {novo.value}.",
        )

    # M3 (§3.5): não inicia produção sem arte aprovada.
    if novo == StatusOs.PRODUCAO:
        from app.services import arte_service

        estado = arte_service.estado_arte(db, os_id=os_id)
        if estado != "aprovada":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Produção não inicia sem arte aprovada pelo cliente "
                    f"(estado da arte: {estado}). Envie a versão e registre a "
                    "aprovação na tela de Arte."
                ),
            )

    os_obj.status = novo
    hoje = date.today()
    if novo == StatusOs.PRONTA and not os_obj.data_conclusao:
        os_obj.data_conclusao = hoje
    if novo == StatusOs.ENTREGUE and not os_obj.data_entrega:
        os_obj.data_entrega = hoje
    db.commit()
    db.refresh(os_obj)
    return _para_out(os_obj)


def converter_em_os(
    db: Session,
    *,
    filial_id: int,
    orcamento_id: int,
    usuario_id: int,
    pagamento_confirmado: bool = False,
) -> OsOut:
    orcamento = buscar(db, orcamento_id, filial_id=filial_id)
    if orcamento.tipo != TipoOs.ORCAMENTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Somente orçamentos podem ser convertidos em ordem de serviço.",
        )
    if orcamento.status != StatusOs.ABERTO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Orçamento deve estar aberto para ser convertido em OS.",
        )

    # M1 (§3.2.2): item de fornecedor SEM cotação selecionada não pode virar
    # OS — iria ao cliente com valor 0. Bloqueia a aprovação com orientação.
    pendentes = [
        (i.descricao_avulsa or f"item {i.seq}").strip()
        for i in orcamento.itens
        if i.tipo == TipoItemOs.FORNECEDOR
        and not any(c.selecionada for c in i.cotacoes)
    ]
    if pendentes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O orçamento tem item de fornecedor sem cotação selecionada: "
                + "; ".join(pendentes)
                + ". Lance e selecione a cotação antes de aprovar."
            ),
        )

    nova = OrdemServico(
        filial_id=filial_id,
        tipo=TipoOs.OS,
        status=StatusOs.ABERTO,
        orcamento_origem_id=orcamento.id,
        cliente_id=orcamento.cliente_id,
        vendedor_id=orcamento.vendedor_id,
        atendente_id=orcamento.atendente_id,
        data_previsao_entrega=orcamento.data_previsao_entrega,
        desconto=orcamento.desconto,
        valor_itens=orcamento.valor_itens,
        valor_total=orcamento.valor_total,
        forma_pagamento=orcamento.forma_pagamento,
        observacoes=orcamento.observacoes,
        criado_por=orcamento.criado_por,
        itens=[
            OrdemServicoItem(
                seq=i.seq,
                produto_id=i.produto_id,
                descricao_avulsa=i.descricao_avulsa,
                quantidade=i.quantidade,
                dimensoes=i.dimensoes,
                valor_unitario=i.valor_unitario,
                desconto=i.desconto,
                valor_total=i.valor_total,
                executado=i.executado,
                tipo=i.tipo,
                snapshot_preco=i.snapshot_preco,
            )
            for i in orcamento.itens
        ],
    )
    orcamento.status = StatusOs.CONVERTIDO
    db.add(nova)
    try:
        db.flush()  # garante nova.id para o lançamento de adiantamento
        # M1 (§3.2.2 item 7): a aprovação gera pedido de compra em rascunho
        # por fornecedor, com o VF cotado (ver §3.7). As cotações ficam nos
        # itens do ORÇAMENTO (histórico/auditoria) — é de lá que se lê.
        _gerar_pedidos_de_compra(
            db,
            filial_id=filial_id,
            usuario_id=usuario_id,
            os_nova=nova,
            orcamento=orcamento,
        )
        adiantamento_service.exigir_e_registrar(
            db,
            filial_id=filial_id,
            usuario_id=usuario_id,
            cliente=orcamento.cliente,
            valor_total=orcamento.valor_total,
            confirmado=pagamento_confirmado,
            documento=f"O.S. #{nova.id}",
            ordem_servico_id=nova.id,
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(nova)
    return _para_out(nova)


def _gerar_pedidos_de_compra(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    os_nova: OrdemServico,
    orcamento: OrdemServico,
) -> None:
    """Pedido de compra em rascunho por fornecedor (M1, §3.2.2 item 7).

    Cada cotação selecionada do ORÇAMENTO vira um item de pedido ao fornecedor
    com o **VF cotado** (o valor interno — nunca vai ao cliente); o pedido fica
    ABERTO/rascunho, ligado à OS por `os_origem_id`, e a cotação recebe
    `pedido_item_id` (o recebimento fecha o ciclo em §3.7).
    """
    por_fornecedor: dict[int, list[tuple[OrdemServicoItem, object]]] = {}
    for item in orcamento.itens:
        if item.tipo != TipoItemOs.FORNECEDOR:
            continue
        selecionada = next((c for c in item.cotacoes if c.selecionada), None)
        if selecionada is None:
            continue  # bloqueado antes; aqui é só defesa
        por_fornecedor.setdefault(selecionada.fornecedor_id, []).append(
            (item, selecionada)
        )

    for fornecedor_id, pares in por_fornecedor.items():
        valor_total = sum((c.vf for _, c in pares), Decimal(0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        prazo = min(
            (c.prazo_dias for _, c in pares if c.prazo_dias is not None),
            default=None,
        )
        pedido = PedidoCompra(
            filial_id=filial_id,
            fornecedor_id=fornecedor_id,
            valor_total=valor_total,
            observacoes=f"Gerado da aprovação da O.S. #{os_nova.id} (item de fornecedor).",
            solicitante_id=usuario_id,
            os_origem_id=os_nova.id,
            status=StatusPedido.ABERTO,
            itens=[],
        )
        db.add(pedido)
        db.flush()  # id para os itens
        for seq, (item, cotacao) in enumerate(pares, start=1):
            item_pedido = PedidoCompraItem(
                pedido_compra_id=pedido.id,
                seq=seq,
                produto_id=None,  # serviço terceirizado: descrição avulsa
                descricao_avulsa=(
                    f"{item.descricao_avulsa or f'item {item.seq}'} — serviço de fornecedor"
                ),
                quantidade=Decimal(1),
                valor_unitario=cotacao.vf,
                valor_total=cotacao.vf,
            )
            db.add(item_pedido)
            db.flush()
            cotacao.pedido_item_id = item_pedido.id
        if prazo is not None:
            pedido.previsao_entrega = date.today() + timedelta(days=prazo)


def _copiar_itens(db: Session, origem: OrdemServico) -> list[OrdemServicoItem]:
    """Copia os itens recalculando o preço dos produtos (§3.10).

    - **Produto próprio**: usa o `preco_venda` vigente do catálogo (é o
      "recalculando preços" do PRD);
    - **Fornecedor**: mantém o snapshot do VO (o VF veio da cotação do
      fornecedor) e **replica as cotações** com a seleção — sem isso o item
      nasceria "aguardando" e travaria a aprovação;
    - **Avulso**: mantém o valor combinado.
    """
    novos: list[OrdemServicoItem] = []
    for seq, item in enumerate(origem.itens, start=1):
        valor = Decimal(item.valor_unitario)
        if item.produto_id and item.tipo == TipoItemOs.PROPRIO:
            produto = db.get(Produto, item.produto_id)
            if produto is not None and produto.preco_venda is not None:
                valor = Decimal(produto.preco_venda)
        total = _q(valor * item.quantidade - item.desconto)
        if total < 0:
            total = Decimal("0.00")
        novo = OrdemServicoItem(
            seq=seq,
            produto_id=item.produto_id,
            descricao_avulsa=item.descricao_avulsa,
            quantidade=item.quantidade,
            dimensoes=item.dimensoes,
            valor_unitario=valor,
            desconto=item.desconto,
            valor_total=total,
            tipo=item.tipo,
            snapshot_preco=item.snapshot_preco,
        )
        for cot in item.cotacoes:
            novo.cotacoes.append(
                OrdemServicoItemCotacao(
                    fornecedor_id=cot.fornecedor_id,
                    vf=cot.vf,
                    validade=cot.validade,
                    prazo_dias=cot.prazo_dias,
                    observacoes=cot.observacoes,
                    selecionada=cot.selecionada,
                    criado_por=cot.criado_por,
                )
            )
        novos.append(novo)
    return novos


def _replicar_arte_aprovada(
    db: Session, *, origem: OrdemServico, destino: OrdemServico, usuario_id: int
) -> bool:
    """Replica a arte **aprovada** para o destino (§3.10).

    "Repetir pedido … com os mesmos itens e arte aprovada": a reimpressão não
    exige nova aprovação do cliente. A versão aprovada é a última enviada
    (o estado deriva dela); o arquivo é o mesmo caminho (somente leitura).
    """
    from app.services import arte_service

    ultima = (
        db.query(ArteVersao)
        .filter(ArteVersao.os_id == origem.id)
        .order_by(ArteVersao.versao.desc())
        .first()
    )
    if ultima is None:
        return False
    if arte_service.estado_arte(db, os_id=origem.id) != "aprovada":
        return False

    nova = ArteVersao(
        filial_id=destino.filial_id,
        os_id=destino.id,
        versao=1,
        nome_arquivo=ultima.nome_arquivo,
        caminho=ultima.caminho,  # mesmo arquivo (somente leitura)
        hash_sha256=ultima.hash_sha256,
        tamanho_bytes=ultima.tamanho_bytes,
        criado_por=usuario_id,
    )
    db.add(nova)
    db.flush()
    db.add(
        ArteAprovacao(
            filial_id=destino.filial_id,
            versao_id=nova.id,
            decisao=DecisaoArte.APROVADA.value,
            comentarios=f"Arte aprovada replicada da O.S. #{origem.numero}.",
            criado_por=usuario_id,
        )
    )
    return True


def repetir_pedido(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    usuario_id: int,
    tipo: TipoOs | None = None,
    pagamento_confirmado: bool = False,
) -> OsOut:
    """Repete um pedido: nova O.S./orçamento com os mesmos itens (§3.10).

    A arte aprovada é replicada (a reimpressão não passa por nova prova) e os
    preços dos produtos são recalculados pelo catálogo vigente. A política de
    sinal do cliente vale como na criação quando o destino é O.S.
    """
    origem = buscar(db, os_id, filial_id=filial_id)
    novo_tipo = tipo or origem.tipo

    itens = _copiar_itens(db, origem)
    valor_itens, valor_total = _totais(itens, Decimal(origem.desconto))
    observacoes = f"Repetição da O.S. #{origem.numero}."
    if origem.observacoes:
        observacoes += f" {origem.observacoes}"

    novo = OrdemServico(
        filial_id=filial_id,
        tipo=novo_tipo,
        status=StatusOs.ABERTO,
        cliente_id=origem.cliente_id,
        vendedor_id=origem.vendedor_id,
        atendente_id=origem.atendente_id,
        desconto=origem.desconto,
        valor_itens=valor_itens,
        valor_total=valor_total,
        forma_pagamento=origem.forma_pagamento,
        observacoes=observacoes,
        criado_por=usuario_id,
        itens=itens,
    )
    db.add(novo)
    try:
        db.flush()
        if novo_tipo == TipoOs.OS:
            cliente = db.get(Cliente, origem.cliente_id) if origem.cliente_id else None
            adiantamento_service.exigir_e_registrar(
                db,
                filial_id=filial_id,
                usuario_id=usuario_id,
                cliente=cliente,
                valor_total=valor_total,
                confirmado=pagamento_confirmado,
                documento=f"O.S. #{novo.id}",
                ordem_servico_id=novo.id,
            )
        replicou = _replicar_arte_aprovada(
            db, origem=origem, destino=novo, usuario_id=usuario_id
        )
        if replicou:
            novo.status = StatusOs.APROVADO
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(novo)
    return _para_out(novo)


def criar_refacao(
    db: Session,
    *,
    filial_id: int,
    os_id: int,
    usuario_id: int,
    motivo: str,
    erro: RefacaoErro,
    responsavel_id: int | None = None,
    custo: Decimal | None = None,
) -> OsOut:
    """Cria a O.S. filha de refação (§3.10).

    A refação reexecuta o serviço: herda os itens (preços recalculados) e a
    arte aprovada, e guarda **motivo**, **responsável**, **custo** e a
    classificação do erro. Erro da **gráfica** não é cobrado do cliente
    (desconto de 100%); erro do **cliente** mantém o desconto original.
    Não aplica a política de sinal — não é uma venda nova.
    """
    origem = buscar(db, os_id, filial_id=filial_id)
    if origem.tipo != TipoOs.OS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Só uma ordem de serviço pode gerar refação.",
        )

    itens = _copiar_itens(db, origem)
    desconto = origem.desconto
    if erro == RefacaoErro.GRAFICA:
        # Erro da gráfica: o cliente não paga pela refação.
        valor_itens = _q(sum((i.valor_total for i in itens), Decimal(0)))
        desconto = valor_itens
    valor_itens, valor_total = _totais(itens, Decimal(desconto))

    motivo_txt = f"Refação da O.S. #{origem.numero} — {motivo.strip()}"
    if origem.observacoes:
        motivo_txt += f". {origem.observacoes}"

    nova = OrdemServico(
        filial_id=filial_id,
        tipo=TipoOs.OS,
        status=StatusOs.ABERTO,
        cliente_id=origem.cliente_id,
        vendedor_id=origem.vendedor_id,
        atendente_id=origem.atendente_id,
        desconto=desconto,
        valor_itens=valor_itens,
        valor_total=valor_total,
        forma_pagamento=origem.forma_pagamento,
        observacoes=motivo_txt,
        criado_por=usuario_id,
        itens=itens,
        refacao_origem_id=origem.id,
        refacao_motivo=motivo.strip(),
        refacao_erro=erro.value,
        refacao_responsavel_id=responsavel_id,
        refacao_custo=_q(Decimal(custo)) if custo is not None else None,
    )
    db.add(nova)
    try:
        db.flush()
        replicou = _replicar_arte_aprovada(
            db, origem=origem, destino=nova, usuario_id=usuario_id
        )
        if replicou:
            nova.status = StatusOs.APROVADO
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise _erro_integridade() from exc
    db.refresh(nova)
    return _para_out(nova)


def cancelar(db: Session, *, filial_id: int, os_id: int) -> None:
    os_obj = buscar(db, os_id, filial_id=filial_id)
    if os_obj.status in (StatusOs.ENTREGUE, StatusOs.CANCELADO, StatusOs.CONVERTIDO):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registro {os_obj.status.value} não pode ser cancelado.",
        )
    os_obj.status = StatusOs.CANCELADO
    db.commit()
