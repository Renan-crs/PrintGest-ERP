"""Serviço de licenciamento `online_periodic` (PRD v2.0 §3) — cliente do RedGest.

O RedGest emite JWT RS256 de curta duração para a licença por CNPJ. Este serviço:

- **ativa**: troca CNPJ + código de licença por credenciais + primeiro token
  (POST `/api/v1/licencas` e `/api/v1/licencas/{id}/ativar`) e guarda tudo na
  tabela local `licenca`;
- **renova**: polling em `/api/v1/licencas/{id}/validar` (PRD §3.2.6 — máquina
  local não recebe webhook), reemitindo o token antes da expiração;
- **modo de leitura**: com token válido o sistema opera completo; sem ativação ou
  com token vencido/revogado, `ESTADO["modo_leitura"]` fica `True` e o middleware
  bloqueia escritas (HTTP 423). Tratado no background pelo loop do lifespan.

Credenciais e endpoints seguem o contrato congelado no `scripts/redgest_stub.py`
(POSTs sem barra final, para o `httpx` não depender de redirect 307).
"""

import asyncio
import datetime as dt
import re

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal
from app.models.licenca import Licenca

STATUS_ATIVA = "ativa"
STATUS_REVOGADA = "revogada"

ESTADO: dict[str, bool] = {"modo_leitura": True}


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _normalizar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _cliente() -> httpx.Client:
    return httpx.Client(base_url=settings.redgest_url, timeout=10.0)


def _garantir_resposta(cliente: httpx.Client, resp: httpx.Response, contexto: str) -> dict:
    if resp.status_code >= 400:
        detalhe = "Erro de comunicação registrado."
        try:
            corpo = resp.json()
            detalhe = corpo.get("detail") or corpo.get("data", {}).get("detail") or detalhe
        except ValueError:
            pass
        codigo = status.HTTP_423_LOCKED if resp.status_code == 403 else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=codigo, detail=f"{contexto}: {detalhe}")
    dados = resp.json().get("data", {})
    return dados


def _licenca_local(db: Session) -> Licenca | None:
    return db.query(Licenca).order_by(Licenca.id).first()


def _recalcular_estado(lic: Licenca | None) -> None:
    valida = (
        lic is not None
        and lic.status == STATUS_ATIVA
        and lic.token_expira_em is not None
        and lic.token_expira_em > _agora()
    )
    ESTADO["modo_leitura"] = not valida


def situacao(db: Session) -> dict:
    lic = _licenca_local(db)
    _recalcular_estado(lic)
    if lic is None:
        return {
            "sistema": settings.redgest_sistema,
            "cnpj": None,
            "codigo_licenca": None,
            "plano": None,
            "status": "nao_ativada",
            "modo_leitura": True,
            "max_estacoes": None,
            "modulos_habilitados": [],
            "token_expira_em": None,
        }
    ent = lic.entitlements or {}
    return {
        "sistema": lic.sistema,
        "cnpj": lic.cnpj,
        "codigo_licenca": lic.codigo_licenca,
        "plano": lic.plano,
        "status": lic.status,
        "modo_leitura": ESTADO["modo_leitura"],
        "max_estacoes": ent.get("max_estacoes"),
        "modulos_habilitados": ent.get("modulos_habilitados") or [],
        "token_expira_em": lic.token_expira_em,
    }


def _persistir_ativa(
    db: Session,
    *,
    licenca_redgest_id: str,
    cnpj: str,
    codigo_licenca: str,
    plano: str | None,
    client_id: str,
    client_secret: str,
    entitlements: dict,
    token: str,
    expires_in: int,
) -> None:
    lic = _licenca_local(db)
    agora = _agora()
    if lic is None:
        lic = Licenca(
            licenca_redgest_id=licenca_redgest_id,
            sistema=settings.redgest_sistema,
            cnpj=cnpj,
            codigo_licenca=codigo_licenca,
        )
        db.add(lic)
    lic.licenca_redgest_id = licenca_redgest_id
    lic.sistema = settings.redgest_sistema
    lic.cnpj = cnpj
    lic.codigo_licenca = codigo_licenca
    lic.plano = plano
    lic.status = STATUS_ATIVA
    lic.client_id = client_id
    lic.client_secret = client_secret
    lic.entitlements = entitlements
    lic.token_jwt = token
    lic.token_expira_em = agora + dt.timedelta(seconds=expires_in)
    lic.ultima_validacao = agora
    db.commit()
    db.refresh(lic)
    _recalcular_estado(lic)


def ativar(db: Session, *, cnpj: str, codigo_licenca: str) -> dict:
    cnpj_limpo = _normalizar_cnpj(cnpj)
    with _cliente() as cliente:
        resp = cliente.post(
            "/api/v1/licencas",
            json={"sistema": settings.redgest_sistema, "cnpj": cnpj_limpo, "codigo_licenca": codigo_licenca},
        )
        dados = _garantir_resposta(cliente, resp, "Falha ao registrar a licença")
        licenca_redgest_id = dados["licenca_id"]

        resp = cliente.post(f"/api/v1/licencas/{licenca_redgest_id}/ativar")
        dados = _garantir_resposta(cliente, resp, "Falha na ativação da licença")
        client_id = dados["client_id"]
        client_secret = dados["client_secret"]
        token = dados["access_token"]
        expires_in = dados["expires_in"]

        resp = cliente.get(f"/api/v1/licencas/{licenca_redgest_id}")
        dados = _garantir_resposta(cliente, resp, "Falha ao consultar a licença")

    entitlements = {
        "cnpj_vinculado": dados.get("cnpj"),
        "max_estacoes": dados.get("max_estacoes"),
        "modulos_habilitados": dados.get("modulos_habilitados") or [],
    }
    _persistir_ativa(
        db,
        licenca_redgest_id=licenca_redgest_id,
        cnpj=cnpj_limpo,
        codigo_licenca=codigo_licenca,
        plano=dados.get("plano"),
        client_id=client_id,
        client_secret=client_secret,
        entitlements=entitlements,
        token=token,
        expires_in=expires_in,
    )
    return situacao(db)


def renovar(db: Session) -> dict:
    lic = _licenca_local(db)
    if lic is None or not lic.client_id or not lic.client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licença ainda não ativada.",
        )
    with _cliente() as cliente:
        resp = cliente.post(
            f"/api/v1/licencas/{lic.licenca_redgest_id}/validar",
            json={"client_id": lic.client_id, "client_secret": lic.client_secret},
        )
        if resp.status_code in (401, 403):
            lic.status = STATUS_REVOGADA
            db.commit()
            _recalcular_estado(lic)
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    "Licença revogada pelo RedGest. O sistema opera em modo de "
                    "leitura — contate o fornecedor para regularizar."
                ),
            )
        dados = _garantir_resposta(cliente, resp, "Falha na renovação da licença")

    agora = _agora()
    lic.status = STATUS_ATIVA
    lic.token_jwt = dados["access_token"]
    lic.token_expira_em = agora + dt.timedelta(seconds=dados["expires_in"])
    lic.ultima_validacao = agora
    lic.entitlements = {
        "cnpj_vinculado": dados.get("cnpj_vinculado"),
        "max_estacoes": dados.get("max_estacoes"),
        "modulos_habilitados": dados.get("modulos_habilitados") or [],
    }
    db.commit()
    db.refresh(lic)
    _recalcular_estado(lic)
    return situacao(db)


def _tentativa_renovacao() -> None:
    db = SessionLocal()
    try:
        lic = _licenca_local(db)
        if lic is None or lic.status != STATUS_ATIVA or lic.token_expira_em is None:
            _recalcular_estado(lic)
            return
        faltando = (lic.token_expira_em - _agora()).total_seconds()
        _recalcular_estado(lic)
        if faltando > settings.licenca_renova_antes_segundos:
            return
        try:
            renovar(db)
        except HTTPException:
            _recalcular_estado(lic)
    finally:
        db.close()


async def loop_renovacao() -> None:
    while True:
        try:
            await asyncio.to_thread(_tentativa_renovacao)
        except Exception:
            pass
        await asyncio.sleep(settings.licenca_refresh_intervalo_segundos)