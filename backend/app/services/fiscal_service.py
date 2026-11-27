"""Serviços do módulo Fiscal (PRD §1.3 / telas_e_fluxos §1.6).

A emissão de NF-e/NFC-e/NFS-e é feita por **API de terceiro**: o PrintGest
monta o payload a partir da venda/O.S., entrega ao gateway configurado na
instalação e acompanha o retorno (chave, protocolo, status). Documentos e
eventos são guardados com escopo de filial — nenhuma credencial do gateway
é persistida.

Funções legadas de consulta (`listar_documentos`, `obter_documento`, `resumo`)
foram mantidas; a emissão antes indisponível agora usa o gateway.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cadastros import Cliente
from app.models.cadastros import Produto
from app.models.core import Empresa, Filial
from app.models.enums import ModeloFiscal, StatusFiscal, StatusVenda
from app.models.fiscal import DocumentoFiscal, FiscalEvento
from app.models.movimento import OrdemServico, VendaBalcao
from app.services import config_service
from app.services.fiscal_gateway import FiscalGateway, GatewayNaoConfigurado

_STATUS_PENDENTES = (
    StatusFiscal.RASCUNHO,
    StatusFiscal.PROCESSANDO,
    StatusFiscal.REJEITADO,
    # Contingência também exige acompanhamento — a UI já conta este status.
    StatusFiscal.CONTINGENCIADO,
)

# Cache curto de disponibilidade para não consultar /health do gateway em
# toda chamada ao resumo (a tela de contingência atualiza sozinha).
# Cache por (filial, URL) — evitar que a disponibilidade de um inquilino
# seja reaproveitada por outro (isolamento multi-tenant).
_DISPONIBILIDADE: dict[tuple[int, str], tuple[float, bool]] = {}
_CACHE_DISPONIBILIDADE_SEGUNDOS = 60

# Fonte única de máscaras (compartilhada com os handlers de log de erro).
from app.core.log_seguranca import (  # noqa: E402
    mascarar_texto as _mascarar_texto,
    sanitizar as _sanitizar,
)


def _ibs_cbs_snapshot(db: Session, *, filial_id: int, data: datetime | None) -> dict | None:
    """Alíquotas vigentes informadas pelo contador — nunca geradas pelo sistema."""
    try:
        empresa = config_service.empresa_atual(db, filial_id=filial_id)
    except HTTPException:
        return None
    aliquota = config_service.aliquota_vigente(
        db, empresa_id=empresa.id, data=data
    )
    if aliquota is None:
        return None
    return {
        "cnae": aliquota.cnae,
        "cbs_pct": str(aliquota.cbs_pct) if aliquota.cbs_pct is not None else None,
        "ibs_uf_pct": (
            str(aliquota.ibs_uf_pct) if aliquota.ibs_uf_pct is not None else None
        ),
        "ibs_municipio_pct": (
            str(aliquota.ibs_municipio_pct)
            if aliquota.ibs_municipio_pct is not None else None
        ),
        "vigencia_inicio": aliquota.vigencia_inicio.isoformat(),
        "fonte": aliquota.fonte,
    }


def _decimal_str(valor: Any) -> str:
    if valor is None:
        return "0.00"
    return str(Decimal(str(valor)).quantize(Decimal("0.01")))


def _base(db: Session, filial_id: int):
    return (
        db.query(DocumentoFiscal, Cliente.nome_razao)
        .outerjoin(Cliente, DocumentoFiscal.cliente_id == Cliente.id)
        .filter(DocumentoFiscal.filial_id == filial_id)
    )


def _item(doc: DocumentoFiscal, cliente_nome: str | None) -> dict:
    dados = {c.name: getattr(doc, c.name) for c in DocumentoFiscal.__table__.columns}
    dados["cliente_nome"] = cliente_nome
    return dados


# ------------------------------------------------------------------- consulta


def listar_documentos(
    db: Session,
    *,
    filial_id: int,
    q: str | None = None,
    modelo: str | None = None,
    status_fiscal: StatusFiscal | None = None,
    contingencia: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    query = _base(db, filial_id)
    if modelo is not None:
        query = query.filter(DocumentoFiscal.modelo == modelo)
    if status_fiscal is not None:
        query = query.filter(DocumentoFiscal.status == status_fiscal)
    if contingencia is not None:
        query = query.filter(DocumentoFiscal.contingencia.is_(contingencia))
    termo = (q or "").strip()
    if termo:
        query = query.filter(
            or_(
                DocumentoFiscal.chave_acesso.ilike(f"%{termo}%"),
                Cliente.nome_razao.ilike(f"%{termo}%"),
                cast(DocumentoFiscal.numero, String).ilike(f"%{termo}%"),
            )
        )
    total = query.count()
    linhas = (
        query.order_by(DocumentoFiscal.created_at.desc(), DocumentoFiscal.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_item(doc, nome) for doc, nome in linhas], total


def obter_documento(db: Session, *, item_id: int, filial_id: int) -> dict:
    linha = _base(db, filial_id).filter(DocumentoFiscal.id == item_id).first()
    if linha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento fiscal não encontrado.",
        )
    doc, nome = linha
    return _item(doc, nome)


def _doc(db: Session, *, item_id: int, filial_id: int) -> DocumentoFiscal:
    doc = (
        db.query(DocumentoFiscal)
        .filter(DocumentoFiscal.id == item_id, DocumentoFiscal.filial_id == filial_id)
        .first()
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Documento fiscal não encontrado.",
        )
    return doc


# -------------------------------------------------------------------- gateway


def invalidar_cache_disponibilidade() -> None:
    """Usado por testes e ao trocar a configuração em tempo de execução."""
    _DISPONIBILIDADE.clear()


def _gateway(db, filial_id: int) -> FiscalGateway:
    """Constrói o gateway com a integração fiscal do banco, se cadastrada."""
    integracao = None
    if db is not None:
        try:
            from app.models.enums import TipoIntegracao
            from app.models.integracao import Integracao

            integracao = (
                db.query(Integracao)
                .filter(
                    Integracao.filial_id == filial_id,
                    Integracao.tipo == TipoIntegracao.FISCAL,
                    Integracao.ativo.is_(True),
                )
                .first()
            )
        except Exception:
            integracao = None
    return FiscalGateway(integracao=integracao, db=db, filial_id=filial_id)


def gateway_configurado(db=None, filial_id: int | None = None) -> bool:
    return _gateway(db, filial_id or 0).configurado


def gateway_disponivel(db=None, filial_id: int | None = None) -> bool:
    gateway = _gateway(db, filial_id or 0)
    chave = (filial_id or 0, gateway.base_url)
    agora = time.monotonic()
    entrada = _DISPONIBILIDADE.get(chave)
    if entrada and agora - entrada[0] < _CACHE_DISPONIBILIDADE_SEGUNDOS:
        return entrada[1]
    disponivel = gateway.health()
    _DISPONIBILIDADE[chave] = (agora, disponivel)
    return disponivel


def gateway_info(db=None, filial_id: int | None = None) -> dict:
    gateway = _gateway(db, filial_id or 0)
    configurado = gateway.configurado
    if not configurado:
        disponivel = False
        mensagem = (
            "Gateway fiscal não configurado — a emissão de NFC-e/NF-e/NFS-e "
            "está indisponível. Configure em Configurações > Integrações "
            "(tipo Fiscal) ou PRINTGEST_FISCAL_GATEWAY_URL. "
            "Os documentos podem ser consultados nesta tela."
        )
    else:
        disponivel = gateway_disponivel(db, filial_id)
        mensagem = (
            "Gateway fiscal operacional — emissão disponível."
            if disponivel
            else "Gateway fiscal configurado, mas sem resposta no momento. "
            "Documentos emitidos ficam em contingência até a consulta."
        )
    return {
        "gateway_configurado": configurado,
        "gateway_disponivel": disponivel,
        "gateway_url": gateway.base_url or None,
        "ambiente": settings.fiscal_gateway_ambiente,
        "mensagem": mensagem,
    }


def resumo(db: Session, *, filial_id: int) -> dict:
    por_status = {
        chave.value: total
        for chave, total in db.query(
            DocumentoFiscal.status, func.count(DocumentoFiscal.id)
        )
        .filter(DocumentoFiscal.filial_id == filial_id)
        .group_by(DocumentoFiscal.status)
        .all()
    }
    por_modelo = {
        chave.value: total
        for chave, total in db.query(
            DocumentoFiscal.modelo, func.count(DocumentoFiscal.id)
        )
        .filter(DocumentoFiscal.filial_id == filial_id)
        .group_by(DocumentoFiscal.modelo)
        .all()
    }
    total = sum(por_status.values())
    pendentes = sum(por_status.get(s.value, 0) for s in _STATUS_PENDENTES)
    em_contingencia = (
        db.query(func.count(DocumentoFiscal.id))
        .filter(
            DocumentoFiscal.filial_id == filial_id,
            DocumentoFiscal.contingencia.is_(True),
        )
        .scalar()
        or 0
    )
    return {
        "total": total,
        "por_status": por_status,
        "por_modelo": por_modelo,
        "pendentes": pendentes,
        "em_contingencia": em_contingencia,
        # Parametrização local para o badge da tela (sem tocar no gateway).
        "ibs_cbs_parametrizado": _ibs_cbs_snapshot(
            db, filial_id=filial_id, data=None
        ) is not None,
        **gateway_info(db, filial_id),
    }


# ------------------------------------------------------------------- auditoria


def registrar_evento(
    db: Session,
    *,
    filial_id: int,
    documento_id: int | None,
    tipo: str,
    mensagem: str | None = None,
    detalhes: dict | None = None,
    criado_por: int | None = None,
) -> FiscalEvento:
    evento = FiscalEvento(
        filial_id=filial_id,
        documento_fiscal_id=documento_id,
        tipo=tipo,
        mensagem=(mensagem or "")[:2000] or None,
        detalhes=_sanitizar(detalhes) if detalhes else None,
        criado_por=criado_por,
    )
    db.add(evento)
    return evento


def listar_eventos(
    db: Session, *, documento_id: int, filial_id: int
) -> list[FiscalEvento]:
    _doc(db, item_id=documento_id, filial_id=filial_id)
    return (
        db.query(FiscalEvento)
        .filter(
            FiscalEvento.documento_fiscal_id == documento_id,
            FiscalEvento.filial_id == filial_id,
        )
        .order_by(FiscalEvento.created_at.asc(), FiscalEvento.id.asc())
        .all()
    )


# ------------------------------------------------------------ montagem payload


def _endereco(dono: Any) -> dict:
    return {
        "logradouro": dono.logradouro,
        "numero": dono.numero,
        "complemento": dono.complemento,
        "bairro": dono.bairro,
        "cidade": dono.cidade,
        "uf": dono.uf,
        "cep": dono.cep,
    }


def _emitente(filial: Filial) -> dict:
    empresa: Empresa | None = filial.empresa
    return {
        "cnpj": filial.cnpj or (empresa.cnpj if empresa else None),
        "nome": empresa.razao_social if empresa else filial.nome,
        "nome_fantasia": (empresa.nome_fantasia if empresa else None) or filial.nome,
        "inscricao_estadual": empresa.inscricao_estadual if empresa else None,
        "inscricao_municipal": empresa.inscricao_municipal if empresa else None,
        "regime_tributario": empresa.regime_tributario if empresa else None,
        "endereco": _endereco(filial),
    }


def _destinatario(cliente: Cliente | None, nome_avulso: str | None) -> dict:
    if cliente is None:
        return {"nome": (nome_avulso or "CONSUMIDOR FINAL").strip() or "CONSUMIDOR FINAL"}
    return {
        "nome": cliente.nome_razao,
        "documento": cliente.cpf_cnpj,
        "inscricao_estadual": cliente.inscricao_estadual,
        "email": cliente.email,
        "endereco": _endereco(cliente),
    }


def _com_ibs_cbs(payload: dict, snapshot: dict | None) -> dict:
    """Bloco aditivo ao payload — DESLIGADO por padrão até validar o gateway."""
    if snapshot and settings.fiscal_enviar_ibs_cbs:
        payload["ibs_cbs"] = snapshot
    return payload


def _payload_venda(
    db: Session, venda: VendaBalcao, *, modelo: ModeloFiscal, contingencia: bool
) -> dict:
    snapshot = _ibs_cbs_snapshot(
        db, filial_id=venda.filial_id, data=venda.data_venda
    )
    return _com_ibs_cbs({
        "modelo": modelo.value,
        "ambiente": settings.fiscal_gateway_ambiente,
        "contingencia": contingencia,
        "referencia": {
            "tipo": "venda_balcao",
            "id": venda.id,
            "numero": venda.numero,
            "data": venda.data_venda.isoformat() if venda.data_venda else None,
        },
        "emitente": _emitente(db.get(Filial, venda.filial_id)),
        "destinatario": _destinatario(venda.cliente, venda.cliente_nome_avulso),
        "valor_total": _decimal_str(venda.valor_total),
        "valor_itens": _decimal_str(venda.valor_itens),
        "desconto": _decimal_str(venda.desconto),
        "pagamento": {
            "forma": str(venda.forma_pagamento.value if hasattr(venda.forma_pagamento, "value") else venda.forma_pagamento),
            "parcelas": venda.parcelas,
            "valor_recebido": _decimal_str(venda.valor_recebido),
            "troco": _decimal_str(venda.troco),
        },
        "itens": [
            {
                "sequencia": item.seq,
                "descricao": item.descricao_avulsa
                or (
                    (db.get(Produto, item.produto_id).nome if item.produto_id else None)
                    or "Item"
                ),
                "quantidade": _decimal_str(item.quantidade),
                "valor_unitario": _decimal_str(item.valor_unitario),
                "desconto": _decimal_str(item.desconto),
                "valor_total": _decimal_str(item.valor_total),
            }
            for item in venda.itens
        ],
    }, snapshot)


def _payload_os(
    db: Session, ordem: OrdemServico, *, modelo: ModeloFiscal, contingencia: bool
) -> dict:
    snapshot = _ibs_cbs_snapshot(db, filial_id=ordem.filial_id, data=None)
    return _com_ibs_cbs({
        "modelo": modelo.value,
        "ambiente": settings.fiscal_gateway_ambiente,
        "contingencia": contingencia,
        "referencia": {
            "tipo": "ordem_servico",
            "id": ordem.id,
            "numero": ordem.numero,
            "data": ordem.data_emissao.isoformat() if ordem.data_emissao else None,
        },
        "emitente": _emitente(db.get(Filial, ordem.filial_id)),
        "destinatario": _destinatario(ordem.cliente, None),
        "valor_total": _decimal_str(ordem.valor_total),
        "valor_itens": _decimal_str(ordem.valor_itens),
        "desconto": _decimal_str(ordem.desconto),
        "pagamento": {
            "forma": str(ordem.forma_pagamento.value if hasattr(ordem.forma_pagamento, "value") else (ordem.forma_pagamento or "")),
            "valor_sinal": _decimal_str(ordem.valor_sinal),
        },
        "itens": [
            {
                "sequencia": item.seq,
                "descricao": item.descricao_avulsa or f"Item {item.seq}",
                "quantidade": _decimal_str(item.quantidade),
                "valor_unitario": _decimal_str(item.valor_unitario),
                "desconto": _decimal_str(item.desconto),
                "valor_total": _decimal_str(item.valor_total),
            }
            for item in ordem.itens
        ],
    }, snapshot)


# --------------------------------------------------------------------- emissão


def _aplicar_retorno(doc: DocumentoFiscal, resultado: Any) -> None:
    """Reflete a resposta do gateway no documento (campos normalizados)."""
    if resultado.gateway_id is not None:
        doc.gateway_id = str(resultado.gateway_id)[:120]
    if resultado.chave_acesso is not None:
        doc.chave_acesso = str(resultado.chave_acesso)[:44]
    if resultado.numero is not None:
        doc.numero = int(resultado.numero)
    if resultado.serie is not None:
        doc.serie = int(resultado.serie)
    if resultado.protocolo is not None:
        doc.protocolo = str(resultado.protocolo)[:30]
    if resultado.mensagem is not None:
        doc.mensagem_retorno = _mascarar_texto(str(resultado.mensagem)[:2000])
    if resultado.xml_url is not None:
        doc.xml_path = str(resultado.xml_url)[:500]
    if resultado.danfe_url is not None:
        doc.danfe_path = str(resultado.danfe_url)[:500]
    doc.retorno_json = _sanitizar(resultado.dados)


def emitir(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int | None,
    modelo: ModeloFiscal,
    venda_balcao_id: int | None = None,
    ordem_servico_id: int | None = None,
    contingencia: bool = False,
) -> dict:
    """Emite via gateway e persiste o documento + evento de auditoria.

    Idempotente para documentos já autorizados/processando: devolve o existente
    em vez de transmitir duas vezes a mesma origem.
    """
    gateway = _gateway(db, filial_id)
    if not gateway.configurado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gateway fiscal não configurado nesta instalação. "
                "Configure em Configurações > Integrações ou defina PRINTGEST_FISCAL_GATEWAY_URL."
            ),
        )
    if bool(venda_balcao_id) == bool(ordem_servico_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe exatamente uma origem: venda_balcao_id ou ordem_servico_id.",
        )

    chave_origem = "venda_balcao_id" if venda_balcao_id else "ordem_servico_id"
    origem_id = venda_balcao_id or ordem_servico_id
    existente = (
        db.query(DocumentoFiscal)
        .filter(
            DocumentoFiscal.filial_id == filial_id,
            DocumentoFiscal.modelo == modelo,
            getattr(DocumentoFiscal, chave_origem) == origem_id,
            DocumentoFiscal.status.in_(
                (StatusFiscal.PROCESSANDO, StatusFiscal.AUTORIZADO)
            ),
        )
        .first()
    )
    if existente is not None:
        return _item(existente, None)

    venda = None
    ordem = None
    if venda_balcao_id:
        venda = (
            db.query(VendaBalcao)
            .filter(VendaBalcao.id == venda_balcao_id, VendaBalcao.filial_id == filial_id)
            .first()
        )
        if venda is None:
            raise HTTPException(404, "Venda de balcão não encontrada.")
        if venda.status != StatusVenda.OK:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Não é possível emitir documento fiscal para venda cancelada.",
            )
        payload = _payload_venda(db, venda, modelo=modelo, contingencia=contingencia)
        valor = venda.valor_total
        cliente_id = venda.cliente_id
    else:
        ordem = (
            db.query(OrdemServico)
            .filter(
                OrdemServico.id == ordem_servico_id,
                OrdemServico.filial_id == filial_id,
            )
            .first()
        )
        if ordem is None:
            raise HTTPException(404, "Ordem de serviço não encontrada.")
        payload = _payload_os(db, ordem, modelo=modelo, contingencia=contingencia)
        valor = ordem.valor_total
        cliente_id = ordem.cliente_id

    doc = DocumentoFiscal(
        filial_id=filial_id,
        modelo=modelo,
        gateway=gateway.__class__.__name__,
        gateway_id=None,
        ambiente=settings.fiscal_gateway_ambiente,
        status=StatusFiscal.RASCUNHO,
        venda_balcao_id=venda_balcao_id,
        ordem_servico_id=ordem_servico_id,
        cliente_id=cliente_id,
        valor_nota=valor,
        contingencia=contingencia,
        tentativas=0,
        criado_por=usuario_id,
    )
    # Snapshot local das alíquotas vigentes (mesmo com envio desligado).
    doc.ibs_cbs_snapshot = payload.get("ibs_cbs") or _ibs_cbs_snapshot(
        db,
        filial_id=filial_id,
        data=venda.data_venda if venda is not None else None,
    )
    db.add(doc)
    db.flush()
    registrar_evento(
        db,
        filial_id=filial_id,
        documento_id=doc.id,
        tipo="emissao_iniciada",
        mensagem=f"Payload montado para {modelo.value}.",
        detalhes={"payload": payload},
        criado_por=usuario_id,
    )
    db.flush()

    try:
        resultado = gateway.emitir(payload)
    except GatewayNaoConfigurado as exc:  # config mudou entre a checagem e a chamada
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    doc.tentativas = (doc.tentativas or 0) + 1
    _aplicar_retorno(doc, resultado)
    if resultado.ok:
        doc.status = resultado.status or StatusFiscal.PROCESSANDO
        registrar_evento(
            db,
            filial_id=filial_id,
            documento_id=doc.id,
            tipo="emitido",
            mensagem=_mascarar_texto(
                resultado.mensagem or "Documento enviado ao gateway."
            ),
            detalhes=resultado.dados,
            criado_por=usuario_id,
        )
    else:
        doc.status = (
            StatusFiscal.CONTINGENCIADO
            if contingencia
            else StatusFiscal.REJEITADO
        )
        registrar_evento(
            db,
            filial_id=filial_id,
            documento_id=doc.id,
            tipo="emissao_falhou",
            mensagem=_mascarar_texto(
                resultado.mensagem or "Falha na emissão via gateway."
            ),
            detalhes=resultado.dados,
            criado_por=usuario_id,
        )

    if venda is not None:
        venda.documento_fiscal_id = doc.id
    db.commit()
    db.refresh(doc)
    return _item(doc, None)


def consultar(
    db: Session, *, item_id: int, filial_id: int, usuario_id: int | None = None
) -> dict:
    doc = _doc(db, item_id=item_id, filial_id=filial_id)
    if not doc.gateway_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Documento ainda não foi enviado ao gateway (sem ID de referência).",
        )
    gateway = _gateway(db, filial_id)  # integração/cofre da filial deste documento
    if not gateway.configurado:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway fiscal não configurado nesta instalação.",
        )
    resultado = gateway.consultar(doc.gateway_id)
    doc.tentativas = (doc.tentativas or 0) + 1
    doc.ultima_consulta_em = datetime.now(UTC)
    if resultado.ok:
        _aplicar_retorno(doc, resultado)
        if resultado.status is not None:
            doc.status = resultado.status
    registrar_evento(
        db,
        filial_id=filial_id,
        documento_id=doc.id,
        tipo="consulta",
        mensagem=_mascarar_texto(
            resultado.mensagem or (
                "Consulta ao gateway concluída." if resultado.ok else "Consulta falhou."
            )
        ),
        detalhes=resultado.dados,
        criado_por=usuario_id,
    )
    db.commit()
    db.refresh(doc)
    return _item(doc, None)


def cancelar(
    db: Session,
    *,
    item_id: int,
    filial_id: int,
    usuario_id: int | None = None,
    motivo: str,
) -> dict:
    doc = _doc(db, item_id=item_id, filial_id=filial_id)
    if doc.status != StatusFiscal.AUTORIZADO:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Só é possível cancelar documento autorizado.",
        )
    if not doc.gateway_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Documento sem ID de referência no gateway.",
        )
    gateway = _gateway(db, filial_id)
    if not gateway.configurado:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway fiscal não configurado nesta instalação.",
        )
    resultado = gateway.cancelar(doc.gateway_id, motivo)
    doc.tentativas = (doc.tentativas or 0) + 1
    if resultado.ok:
        _aplicar_retorno(doc, resultado)
        doc.status = StatusFiscal.CANCELADO
        doc.cancelado_em = datetime.now(UTC)
        doc.motivo_cancelamento = motivo
    registrar_evento(
        db,
        filial_id=filial_id,
        documento_id=doc.id,
        tipo="cancelamento" if resultado.ok else "cancelamento_falhou",
        mensagem=_mascarar_texto(
            resultado.mensagem or (
                "Cancelamento enviado ao gateway."
                if resultado.ok else "Cancelamento falhou."
            )
        ),
        detalhes=resultado.dados,
        criado_por=usuario_id,
    )
    db.commit()
    db.refresh(doc)
    return _item(doc, None)
