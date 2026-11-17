"""Consolidação de leitura no Neon (PRD v3.3 §5.3/§5.6).

- **Mestres**: a MATRIZ publica produto/fornecedor no outbox; o trigger do Neon
  mantém `consolidado.mestre` com versão. A filial **desce** por `versao >
  cursor` e aplica no banco local (RF-SY-05). Respeita snapshot de orçamentos
  já emitidos — os mestres não alteram registros antigos.
- **Conflitos de clientes**: duplicatas por CPF/CNPJ entre filiais vão para
  uma fila lida do Neon; a Gerente da matriz resolve (RF-FL-04).
- **Relatórios consolidados**: faturamento/margem por filial lidos da view
  `consolidado.vw_vendas`, com rótulo de defasagem (§5.6).

Toda leitura usa o role da filial (RLS) e o cofre `cofre_sync`. Nenhuma
credencial aparece em log/resposta.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

import psycopg
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import cofre_sync
from app.models.cadastros import Cliente, Fornecedor, Produto
from app.models.consolidacao import SyncEstado
from app.services import filial_service

_MESTRES = ("mestre:produto", "mestre:fornecedor")


def _conectar(filial_id: int):
    url = cofre_sync.url(filial_id)
    if not url:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Consolidação não configurada para esta filial.",
        )
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return psycopg.connect(url, connect_timeout=10)


def _cursor(db: Session, filial_id: int, entidade: str) -> int:
    linha = (
        db.query(SyncEstado)
        .filter(
            SyncEstado.filial_id == filial_id,
            SyncEstado.entidade == entidade,
        )
        .first()
    )
    return int(linha.ultima_versao) if linha else 0


def _salvar_cursor(
    db: Session, filial_id: int, entidade: str, versao: int
) -> None:
    linha = (
        db.query(SyncEstado)
        .filter(
            SyncEstado.filial_id == filial_id,
            SyncEstado.entidade == entidade,
        )
        .first()
    )
    if linha is None:
        linha = SyncEstado(
            filial_id=filial_id, entidade=entidade, ultima_versao=versao
        )
        db.add(linha)
    else:
        linha.ultima_versao = max(int(linha.ultima_versao), versao)
    linha.ultimo_aplicado_em = datetime.now(UTC)
    db.commit()


# ------------------------------------------------------------------ mestres


def publicar_mestre(
    db: Session, *, filial_id: int, entidade: str, chave: str, payload: dict
) -> dict:
    """Publica um cadastro mestre no outbox (chamado pela MATRIZ)."""
    if entidade not in _MESTRES:
        raise HTTPException(400, f"Entidade mestre desconhecida: {entidade}")
    ev = filial_service.registrar_evento(
        db,
        filial_id=filial_id,
        entidade=entidade,
        entidade_id=None,
        operacao="Mestre",
        payload={"chave": chave, **payload},
    )
    db.commit()
    db.refresh(ev)
    return {"uuid": ev.uuid, "entidade": entidade, "seq": ev.seq}


def descer_mestres(
    db: Session, *, filial_id: int, conexao=None
) -> dict:
    """Aplica mestres com versão maior que o cursor local (RF-SY-05)."""
    dono = conexao is None
    conn = conexao or _conectar(filial_id)
    aplicados: dict[str, int] = {}
    erros: list[str] = []
    try:
        with conn.cursor() as cur:
            for entidade in _MESTRES:
                cursor = _cursor(db, filial_id, entidade)
                cur.execute(
                    "SELECT versao, payload FROM consolidado.mestre "
                    "WHERE entidade = %s AND versao > %s ORDER BY versao",
                    (entidade, cursor),
                )
                linhas = cur.fetchall()
                maior = cursor
                modelo = Produto if entidade == "mestre:produto" else Fornecedor
                for versao, payload in linhas:
                    dados = payload if isinstance(payload, dict) else json.loads(payload)
                    chave = str(dados.get("chave") or "").strip()
                    if not chave:
                        continue
                    existente = (
                        db.query(modelo)
                        .filter(
                            modelo.filial_id == filial_id,
                            modelo.codigo == chave
                            if modelo is Produto
                            else modelo.cpf_cnpj == chave,
                        )
                        .first()
                    )
                    if existente is None:
                        novo = modelo(filial_id=filial_id)
                        setattr(
                            novo,
                            "codigo" if modelo is Produto else "cpf_cnpj",
                            chave,
                        )
                        if modelo is Produto:
                            novo.nome = dados.get("nome") or chave
                            novo.tipo_produto = dados.get("tipo_produto", "produto")
                            if dados.get("preco_venda") is not None:
                                novo.preco_venda = Decimal(str(dados["preco_venda"]))
                        else:
                            novo.nome_razao = dados.get("nome") or chave
                        db.add(novo)
                    else:
                        if dados.get("nome"):
                            if modelo is Produto:
                                existente.nome = dados["nome"]
                            else:
                                existente.nome_razao = dados["nome"]
                    maior = max(maior, int(versao))
                if maior > cursor:
                    db.commit()
                    _salvar_cursor(db, filial_id, entidade, maior)
                    aplicados[entidade] = maior - cursor
    except Exception as exc:
        if dono:
            conn.rollback()
        logger.exception("Falha na descida de mestres (filial=%s)", filial_id)
        erros.append(f"Falha na descida: {type(exc).__name__}: {exc}")
    finally:
        if dono:
            conn.close()
    return {"aplicados": aplicados, "erros": erros, "ok": not erros}


# ----------------------------------------------------------------- conflitos


def conflitos(
    db: Session, *, filial_id: int, conexao=None, limit: int = 50
) -> dict:
    """Duplicatas de cliente por documento entre filiais (RF-FL-04)."""
    dono = conexao is None
    conn = conexao or _conectar(filial_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload->>'cpf_cnpj' AS documento, "
                "array_agg(DISTINCT filial_id) AS filiais, "
                "count(DISTINCT filial_id) AS qtd "
                "FROM consolidado.evento_sync "
                "WHERE entidade = 'cliente' "
                "AND NULLIF(payload->>'cpf_cnpj','') IS NOT NULL "
                "GROUP BY 1 HAVING count(DISTINCT filial_id) > 1 "
                "ORDER BY qtd DESC, documento LIMIT %s",
                (limit,),
            )
            linhas = cur.fetchall()
    except Exception as exc:
        if dono:
            conn.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha ao consultar conflitos: {type(exc).__name__}.",
        ) from exc
    finally:
        if dono:
            conn.close()
    return {
        "total": len(linhas),
        "itens": [
            {"documento": d, "filiais": list(f or []), "quantidade": int(q)}
            for d, f, q in linhas
        ],
    }


def resolver_conflito(
    db: Session,
    *,
    filial_id: int,
    documento: str,
    filial_escolhida: int,
    uuid_escolhido: str,
    usuario_id: int,
    conexao=None,
) -> dict:
    """Registra a decisão da Gerente da matriz no Neon."""
    dono = conexao is None
    conn = conexao or _conectar(filial_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO consolidado.cliente_conflito_resolucao "
                "(documento, filial_escolhida, uuid_escolhido, resolvido_por) "
                "VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (documento) DO UPDATE SET "
                "filial_escolhida=EXCLUDED.filial_escolhida, "
                "uuid_escolhido=EXCLUDED.uuid_escolhido, "
                "resolvido_por=EXCLUDED.resolvido_por, resolvido_em=now()",
                (documento, filial_escolhida, uuid_escolhido, usuario_id),
            )
        conn.commit()
        return {"ok": True, "documento": documento}
    except Exception as exc:
        if dono:
            conn.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha ao resolver conflito: {type(exc).__name__}.",
        ) from exc
    finally:
        if dono:
            conn.close()


# ---------------------------------------------------------------- relatórios


def relatorio_vendas(
    db: Session,
    *,
    filial_id: int,
    de: str | None = None,
    ate: str | None = None,
    conexao=None,
) -> dict:
    """Faturamento por filial via `consolidado.vw_vendas` (§5.6)."""
    dono = conexao is None
    conn = conexao or _conectar(filial_id)
    sql = (
        "SELECT filial_id, count(*) AS qtd, "
        "coalesce(sum(valor_total),0) AS total "
        "FROM consolidado.vw_vendas WHERE 1=1"
    )
    params: list = []
    if de:
        sql += " AND data_venda >= %s"
        params.append(de)
    if ate:
        sql += " AND data_venda <= %s"
        params.append(ate)
    sql += " GROUP BY filial_id ORDER BY filial_id"
    try:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            linhas = cur.fetchall()
            cur.execute("SELECT max(criado_em) FROM consolidado.vw_vendas")
            defasagem = cur.fetchone()[0]
    except Exception as exc:
        if dono:
            conn.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Falha no relatório consolidado: {type(exc).__name__}.",
        ) from exc
    finally:
        if dono:
            conn.close()
    return {
        "por_filial": [
            {
                "filial_id": int(f),
                "quantidade": int(q),
                "total": str(t),
            }
            for f, q, t in linhas
        ],
        "ultima_atualizacao": (
            defasagem.isoformat()
            if hasattr(defasagem, "isoformat")
            else (str(defasagem) if defasagem else None)
        ),
        "total_geral": str(sum(Decimal(str(t)) for _, _, t in linhas)),
        "observacao": "Dados do Neon — podem apresentar defasagem.",
    }
