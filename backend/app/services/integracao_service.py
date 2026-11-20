"""Serviço de integrações com apps de terceiros (PRD v3.3 §3.6).

Segredos (API key/token, certificado) ficam **somente** no cofre do SO
(`cofre_integracoes`). O banco guarda metadados e máscaras. Nenhuma função
deste módulo devolve o segredo — o teste de conexão usa o valor direto do
cofre e mascara qualquer ocorrência no retorno/log.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core import cofre_integracoes
from app.models.core import Usuario
from app.models.enums import TipoIntegracao
from app.models.integracao import Integracao, IntegracaoEvento

_SEGREDOS = re.compile(
    r"(authorization|api[_-]?key|token|secret|senha|password|certificado)",
    re.IGNORECASE,
)


def _erro_integridade() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail="Já existe uma integração deste tipo para a filial.",
    )


def listar(db: Session, *, filial_id: int) -> dict:
    itens = (
        db.query(Integracao)
        .filter(Integracao.filial_id == filial_id)
        .order_by(Integracao.tipo, Integracao.id)
        .all()
    )
    total = len(itens)
    return {
        "data": [_para_out(i) for i in itens],
        "total": total,
        "meta": {"total": total, "limit": max(total, 1), "offset": 0},
    }


def obter(db: Session, *, item_id: int, filial_id: int) -> Integracao:
    item = (
        db.query(Integracao)
        .filter(Integracao.id == item_id, Integracao.filial_id == filial_id)
        .first()
    )
    if item is None:
        raise HTTPException(404, "Integração não encontrada.")
    return item


def _para_out(item: Integracao) -> dict:
    return {c.name: getattr(item, c.name) for c in Integracao.__table__.columns}


def _sincronizar_mascaras(db: Session, item: Integracao) -> None:
    item.credencial_mascara = cofre_integracoes.mascara(
        cofre_integracoes.obter(item.filial_id, item.id, "credencial")
    )
    item.certificado_mascara = cofre_integracoes.mascara(
        cofre_integracoes.obter(item.filial_id, item.id, "certificado")
    )
    item.tem_credencial = bool(item.credencial_mascara)
    item.tem_certificado = bool(item.certificado_mascara)


def registrar_evento(
    db: Session,
    *,
    filial_id: int,
    integracao_id: int | None,
    tipo: str,
    mensagem: str | None = None,
    detalhes: dict | None = None,
    criado_por: int | None = None,
) -> IntegracaoEvento:
    evento = IntegracaoEvento(
        filial_id=filial_id,
        integracao_id=integracao_id,
        tipo=tipo,
        mensagem=(mensagem or "")[:2000] or None,
        detalhes=_sanitizar(detalhes) if detalhes else None,
        criado_por=criado_por,
    )
    db.add(evento)
    return evento


def _sanitizar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {
            ch: (
                "***"
                if _SEGREDOS.search(str(ch))
                else _sanitizar(item)
            )
            for ch, item in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [_sanitizar(i) for i in valor]
    if isinstance(valor, str) and _SEGREDOS.search(valor):
        return "***"
    return valor


def eventos(db: Session, *, item_id: int, filial_id: int) -> list[IntegracaoEvento]:
    obter(db, item_id=item_id, filial_id=filial_id)
    return (
        db.query(IntegracaoEvento)
        .filter(
            IntegracaoEvento.integracao_id == item_id,
            IntegracaoEvento.filial_id == filial_id,
        )
        .order_by(IntegracaoEvento.created_at, IntegracaoEvento.id)
        .all()
    )


def criar(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    dados: dict,
) -> dict:
    segredo = dados.pop("credencial", None)
    certificado = dados.pop("certificado", None)
    item = Integracao(filial_id=filial_id, criado_por=usuario_id, **dados)
    db.add(item)
    try:
        db.flush()  # id para as chaves do cofre
    except Exception as exc:
        db.rollback()
        if "uq_integracao_filial_tipo" in str(exc).lower():
            raise _erro_integridade() from exc
        raise

    if segredo:
        cofre_integracoes.definir(filial_id, item.id, "credencial", segredo)
    if certificado:
        cofre_integracoes.definir(filial_id, item.id, "certificado", certificado)
    _sincronizar_mascaras(db, item)
    registrar_evento(
        db,
        filial_id=filial_id,
        integracao_id=item.id,
        tipo="CRIADA",
        mensagem=f"Integração {dados.get('tipo')} criada.",
        detalhes={"provedor": dados.get("provedor")},
        criado_por=usuario_id,
    )
    db.commit()
    db.refresh(item)
    return _para_out(item)


def atualizar(
    db: Session, *, item_id: int, filial_id: int, usuario_id: int, dados: dict
) -> dict:
    item = obter(db, item_id=item_id, filial_id=filial_id)
    segredo = dados.pop("credencial", None)
    certificado = dados.pop("certificado", None)
    remover_credencial = bool(dados.pop("remover_credencial", False))
    remover_certificado = bool(dados.pop("remover_certificado", False))

    for chave, valor in dados.items():
        if valor is not None:
            setattr(item, chave, valor)
    if segredo is not None:
        cofre_integracoes.definir(filial_id, item.id, "credencial", segredo)
    if certificado is not None:
        cofre_integracoes.definir(filial_id, item.id, "certificado", certificado)
    if remover_credencial:
        cofre_integracoes.definir(filial_id, item.id, "credencial", None)
    if remover_certificado:
        cofre_integracoes.definir(filial_id, item.id, "certificado", None)
    _sincronizar_mascaras(db, item)
    registrar_evento(
        db,
        filial_id=filial_id,
        integracao_id=item.id,
        tipo="ATUALIZADA",
        mensagem="Configuração da integração atualizada.",
        detalhes={"campos": sorted(dados.keys())},
        criado_por=usuario_id,
    )
    db.commit()
    db.refresh(item)
    return _para_out(item)


def excluir(db: Session, *, item_id: int, filial_id: int, usuario_id: int) -> None:
    item = obter(db, item_id=item_id, filial_id=filial_id)
    cofre_integracoes.remover_integracao(filial_id, item.id)
    # Mantém a auditoria (eventos passam a ter integracao_id = NULL) antes
    # de apagar o registro — o FK não permite exclusão com eventos ligados.
    db.query(IntegracaoEvento).filter(
        IntegracaoEvento.integracao_id == item.id
    ).update({IntegracaoEvento.integracao_id: None}, synchronize_session=False)
    registrar_evento(
        db,
        filial_id=filial_id,
        integracao_id=None,
        tipo="EXCLUIDA",
        mensagem=f"Integração {item.tipo} excluída.",
        criado_por=usuario_id,
    )
    db.delete(item)
    db.commit()


def testar(
    db: Session, *, item_id: int, filial_id: int, usuario_id: int | None = None
) -> dict:
    """Teste de conexão: GET na base URL com o segredo do cofre no cabeçalho.

    O valor do segredo NUNCA entra na resposta nem no evento.
    """
    item = obter(db, item_id=item_id, filial_id=filial_id)
    if not item.base_url:
        raise HTTPException(400, "Informe a URL base da integração antes de testar.")
    segredo = cofre_integracoes.obter(filial_id, item.id, "credencial")
    if not segredo and item.tem_certificado is False:
        raise HTTPException(
            400,
            "Insira a credencial ou o certificado de API antes de testar.",
        )
    cabecalhos = {"Accept": "application/json"}
    if segredo:
        cabecalhos[item.auth_header or "Authorization"] = (
            f"{item.auth_prefix or ''}{segredo}"
        )
    agora = datetime.now(UTC)
    try:
        with httpx.Client(timeout=10) as cliente:
            resposta = cliente.get(item.base_url.rstrip("/"), headers=cabecalhos)
        ok = 200 <= resposta.status_code < 400
        mensagem = (
            "Conexão bem-sucedida."
            if ok
            else f"O provedor respondeu HTTP {resposta.status_code}."
        )
        status_http: int | None = resposta.status_code
    except (httpx.HTTPError, OSError) as exc:
        ok = False
        mensagem = f"Falha de comunicação: {type(exc).__name__}."
        status_http = None

    item.ultimo_teste_em = agora
    item.ultimo_teste_ok = ok
    registrar_evento(
        db,
        filial_id=filial_id,
        integracao_id=item.id,
        tipo="TESTE_OK" if ok else "TESTE_FALHA",
        mensagem=mensagem,
        detalhes={"status_http": status_http},
        criado_por=usuario_id,
    )
    db.commit()
    return {
        "ok": ok,
        "status_http": status_http,
        "mensagem": mensagem,
        "testado_em": agora,
        "segredo_exposto": False,
    }


def usar_credencial(db: Session, *, filial_id: int, tipo: TipoIntegracao) -> str:
    """Uso interno (ex.: gateway fiscal): devolve a credencial em claro ao
    chamador autorizado. NUNCA chamar em resposta de API."""
    item = (
        db.query(Integracao)
        .filter(
            Integracao.filial_id == filial_id,
            Integracao.tipo == tipo,
            Integracao.ativo.is_(True),
        )
        .first()
    )
    if item is None:
        return ""
    return cofre_integracoes.obter(filial_id, item.id, "credencial")
