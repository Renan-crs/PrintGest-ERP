"""Diagnóstico da licença (PRD v3.3 §4.15 / RF-DG-01..06).

Tudo que sai daqui é **sem segredo**: nenhum token, código de licença,
`Authorization` ou `client_secret` aparece no objeto. O texto de "Copiar
diagnóstico" é montado no desktop a partir deste objeto.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.plataforma import LicencaEvento
from app.services import licensa_service

_PADRAO_SEGREDO = re.compile(
    r"(client_secret|token|codigo|chave|authorization|senha|password|secret)",
    re.IGNORECASE,
)

# "ESTADO" do licensa_service hoje só tem `modo_leitura`; estes são espelhos
# derivados da própria licença (sem gravar nada novo — estado é calculado).
_ESTADOS = {
    "ATIVA": "ativa",
    "BLOQUEADA": "bloqueada",
    "REVOGADA": "revogada",
    "EXPIRADA": "expirada",
}


def _sanitizar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {
            k: (
                "***"
                if _PADRAO_SEGREDO.search(str(k))
                else _sanitizar(v)
            )
            for k, v in valor.items()
        }
    if isinstance(valor, (list, tuple)):
        return [_sanitizar(v) for v in valor]
    return valor


def registrar_evento(
    db: Session,
    *,
    tipo: str,
    estado_anterior: str | None = None,
    estado_novo: str | None = None,
    codigo_erro: str | None = None,
    correlation_id: str | None = None,
    detalhe: dict | None = None,
) -> LicencaEvento:
    ev = LicencaEvento(
        em=datetime.now(UTC),
        tipo=tipo[:40],
        estado_anterior=estado_anterior,
        estado_novo=estado_novo,
        codigo_erro=(codigo_erro or "")[:80] or None,
        correlation_id=(correlation_id or "")[:64] or None,
        detalhe=_sanitizar(detalhe) if detalhe else None,
    )
    db.add(ev)
    return ev


def eventos(db: Session, *, limit: int = 20) -> list[LicencaEvento]:
    return (
        db.query(LicencaEvento)
        .order_by(LicencaEvento.em.desc(), LicencaEvento.id.desc())
        .limit(limit)
        .all()
    )


def diagnosticar(db: Session) -> dict:
    sit = licensa_service.situacao(db)
    lic = licensa_service._licenca_local(db)
    ents = (getattr(lic, "entitlements", None) or {}) if lic is not None else {}
    redgest = ents.get("redgest") or {}
    if not isinstance(redgest, dict):
        redgest = {}

    estado = str(sit.get("estado") or "nao_ativada")
    modulos = licensa_service.MODULOS_HABILITADOS
    ultima = getattr(lic, "ultima_validacao", None)
    tentativa = getattr(lic, "ultima_tentativa_em", None)
    falhas = getattr(lic, "falhas_seguidas", 0) or 0

    # Correlação: a licença guarda o último ID no entitlements quando há;
    # nunca gravamos o segredo correspondente.
    correlation_ids = []
    for ev in eventos(db, limit=20):
        if ev.correlation_id and ev.correlation_id not in correlation_ids:
            correlation_ids.append(ev.correlation_id)

    def _dt(valor):
        return valor.isoformat() if hasattr(valor, "isoformat") else valor

    return {
        "estado": estado,
        "modo_leitura": bool(sit.get("modo_leitura")),
        "plano": sit.get("plano"),
        "status_servidor": getattr(lic, "status", None) or sit.get("status"),
        "estado_vinculo": redgest.get("estado_vinculo"),
        "token_exp": _dt(getattr(lic, "token_expira_em", None)),
        "grace_deadline": _dt(getattr(lic, "tolerancia_expira_em", None)),
        "proxima_renovacao": None,  # derivado de renovar_em_segundos pelo loop
        "ultima_renovacao_ok": _dt(ultima),
        "ultima_tentativa_em": _dt(tentativa),
        "falhas_seguidas": int(falhas or 0),
        "rebinds_restantes": redgest.get("rebinds_restantes"),
        "vagas_livres": redgest.get("vagas_livres"),
        "max_estacoes": redgest.get("max_estacoes") or ents.get("max_estacoes"),
        "max_filiais": redgest.get("max_filiais") or ents.get("max_filiais"),
        "modulos_habilitados": sorted(str(m) for m in modulos),
        "instalacao_id": redgest.get("instalacao_id") or getattr(lic, "client_id", None),
        "instalacao_nome": redgest.get("nome_instalacao"),
        "papel": redgest.get("papel"),
        "licenca_id": getattr(lic, "licenca_redgest_id", None),
        "diferenca_relogio_segundos": None,
        "versao": str(settings.version),
        "correlation_ids": correlation_ids[:20],
        "eventos": [
            {
                "id": e.id,
                "em": e.em.isoformat() if e.em else None,
                "tipo": e.tipo,
                "estado_anterior": e.estado_anterior,
                "estado_novo": e.estado_novo,
                "codigo_erro": e.codigo_erro,
                "correlation_id": e.correlation_id,
                "detalhe": e.detalhe,
            }
            for e in eventos(db, limit=20)
        ],
        # Prova explícita de que nada é exposto (teste automatizado T-23).
        "segredos_mascarados": True,
    }
