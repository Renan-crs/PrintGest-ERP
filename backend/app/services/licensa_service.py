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

Resiliência (`docs/plano_resiliencia_licenca.md`): o timeout para o RedGest é
configurável (padrão 90 s, para absorver *cold start* de plano gratuito) e as
falhas de transporte viram `503` com mensagem clara — nunca revogação. O loop
aplica backoff crescente (1/5/15 min) entre tentativas que falham.

Credenciais e endpoints seguem o contrato congelado no `scripts/redgest_stub.py`
(POSTs sem barra final, para o `httpx` não depender de redirect 307).
"""

import asyncio
import datetime as dt
import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import SessionLocal
from app.models.licenca import Licenca

logger = logging.getLogger(__name__)

STATUS_ATIVA = "ativa"
STATUS_REVOGADA = "revogada"

ESTADO: dict[str, bool] = {"modo_leitura": not settings.licenca_desabilitada}


def _desabilitada() -> bool:
    return settings.licenca_desabilitada


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _normalizar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", cnpj)


def _cliente() -> httpx.Client:
    return httpx.Client(
        base_url=settings.redgest_url, timeout=settings.licenca_timeout_segundos
    )


def _indisponivel(contexto: str, exc: Exception) -> HTTPException:
    """Traduz falha de transporte (timeout/DNS/conexão) em 503 com mensagem clara.

    Distingue "RedGest inacessível" de "licença revogada": só a resposta
    explícita de revogação (401/403) leva ao modo de leitura; indisponibilidade
    de rede não.
    """
    logger.warning("RedGest inacessível (%s): %s", contexto, exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Não foi possível falar com o servidor de licenças "
            f"({contexto}). Verifique a conexão e tente novamente."
        ),
    )


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
    try:
        corpo = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{contexto}: resposta não-JSON do servidor de licenças.",
        ) from exc
    return corpo.get("data", {})


def _campo(dados: dict, chave: str, contexto: str) -> Any:
    """Extrai campo obrigatório do payload do RedGest com erro claro (P4).

    Evita `KeyError` → HTTP 500 quando o servidor externo responde 2xx com
    payload incompleto; converte em 502 (Bad Gateway) com mensagem acionável.
    """
    valor = dados.get(chave)
    if valor is None or valor == "":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Resposta inválida do servidor de licenças "
                f"({contexto}: campo '{chave}' ausente)."
            ),
        )
    return valor


def _licenca_local(db: Session) -> Licenca | None:
    return db.query(Licenca).order_by(Licenca.id).first()


ESTADO_ATIVA = "ativa"
ESTADO_TOLERANCIA = "tolerancia"
ESTADO_LEITURA = "leitura"
ESTADO_REVOGADA = "revogada"
ESTADO_NAO_ATIVADA = "nao_ativada"


def _janela_tolerancia(token_expira_em: dt.datetime) -> dt.datetime:
    return token_expira_em + dt.timedelta(hours=settings.licenca_tolerancia_horas)


def _tolerancia_expira_em(lic: Licenca) -> dt.datetime | None:
    """Tolerância efetiva: a coluna, ou derivada do token (bases anteriores a E2).

    Licenças ativadas antes da migração `c9e4f1a7b2d8` não têm a coluna; derivar
    aqui evita que essas bases percam a tolerância até a próxima renovação.
    """
    if lic.tolerancia_expira_em is not None:
        return lic.tolerancia_expira_em
    if lic.token_expira_em is None:
        return None
    return _janela_tolerancia(lic.token_expira_em)


def _estado(lic: Licenca | None) -> str:
    """Estado derivado (plano E2): ativa | tolerancia | leitura | revogada | nao_ativada."""
    if lic is None:
        return ESTADO_NAO_ATIVADA
    if lic.status == STATUS_REVOGADA:
        return ESTADO_REVOGADA
    if lic.status != STATUS_ATIVA or lic.token_expira_em is None:
        return ESTADO_LEITURA
    agora = _agora()
    if lic.token_expira_em > agora:
        return ESTADO_ATIVA
    tolerancia = _tolerancia_expira_em(lic)
    if tolerancia is not None and tolerancia > agora:
        return ESTADO_TOLERANCIA
    return ESTADO_LEITURA


def _modo_leitura(estado: str) -> bool:
    return estado in (ESTADO_LEITURA, ESTADO_REVOGADA, ESTADO_NAO_ATIVADA)


def _motivo(estado: str) -> str:
    return {
        ESTADO_ATIVA: "Licença ativa.",
        ESTADO_TOLERANCIA: (
            "Sem contato com o RedGest; operando normalmente em tolerância."
        ),
        ESTADO_REVOGADA: "Licença revogada pelo RedGest.",
        ESTADO_NAO_ATIVADA: "Licença ainda não ativada.",
    }.get(estado, "Tolerância esgotada ou licença inválida.")


def _recalcular_estado(lic: Licenca | None) -> None:
    ESTADO["modo_leitura"] = _modo_leitura(_estado(lic))


def situacao(db: Session) -> dict:
    lic = _licenca_local(db)
    estado = _estado(lic)
    ESTADO["modo_leitura"] = _modo_leitura(estado)
    if _desabilitada():
        ESTADO["modo_leitura"] = False
    if lic is None:
        return {
            "sistema": settings.redgest_sistema,
            "cnpj": None,
            "plano": None,
            "status": ESTADO_NAO_ATIVADA,
            "estado": estado,
            "motivo": _motivo(estado),
            "modo_leitura": ESTADO["modo_leitura"],
            "max_estacoes": None,
            "modulos_habilitados": [],
            "token_expira_em": None,
            "tolerancia_expira_em": None,
            "ultima_tentativa_em": None,
            "ultimo_erro": None,
        }
    ent = lic.entitlements or {}
    return {
        "sistema": lic.sistema,
        "cnpj": lic.cnpj,
        "plano": lic.plano,
        "status": lic.status,
        "estado": estado,
        "motivo": _motivo(estado),
        "modo_leitura": ESTADO["modo_leitura"],
        "max_estacoes": ent.get("max_estacoes"),
        "modulos_habilitados": ent.get("modulos_habilitados") or [],
        "token_expira_em": lic.token_expira_em,
        "tolerancia_expira_em": _tolerancia_expira_em(lic),
        "ultima_tentativa_em": lic.ultima_tentativa_em,
        "ultimo_erro": lic.ultimo_erro,
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
    lic.tolerancia_expira_em = _janela_tolerancia(lic.token_expira_em)
    lic.ultima_validacao = agora
    lic.ultima_tentativa_em = agora
    lic.ultimo_erro = None
    db.commit()
    db.refresh(lic)
    _recalcular_estado(lic)


def ativar(db: Session, *, cnpj: str, codigo_licenca: str) -> dict:
    if _desabilitada():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licenciamento desabilitado nesta build de desenvolvimento.",
        )
    cnpj_limpo = _normalizar_cnpj(cnpj)
    try:
        with _cliente() as cliente:
            resp = cliente.post(
                "/api/v1/licencas",
                json={"sistema": settings.redgest_sistema, "cnpj": cnpj_limpo, "codigo_licenca": codigo_licenca},
            )
            dados = _garantir_resposta(cliente, resp, "Falha ao registrar a licença")
            licenca_redgest_id = _campo(dados, "licenca_id", "registro")

            resp = cliente.post(f"/api/v1/licencas/{licenca_redgest_id}/ativar")
            dados = _garantir_resposta(cliente, resp, "Falha na ativação da licença")
            client_id = _campo(dados, "client_id", "ativação")
            client_secret = _campo(dados, "client_secret", "ativação")
            token = _campo(dados, "access_token", "ativação")
            expires_in = int(_campo(dados, "expires_in", "ativação"))

            resp = cliente.get(f"/api/v1/licencas/{licenca_redgest_id}")
            dados = _garantir_resposta(cliente, resp, "Falha ao consultar a licença")
    except httpx.HTTPError as exc:
        raise _indisponivel("ativação", exc) from exc

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
    if _desabilitada():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licenciamento desabilitado nesta build de desenvolvimento.",
        )
    lic = _licenca_local(db)
    if lic is None or not lic.client_id or not lic.client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licença ainda não ativada.",
        )
    with _cliente() as cliente:
        try:
            resp = cliente.post(
                f"/api/v1/licencas/{lic.licenca_redgest_id}/validar",
                json={"client_id": lic.client_id, "client_secret": lic.client_secret},
            )
        except httpx.HTTPError as exc:
            lic.ultima_tentativa_em = _agora()
            lic.ultimo_erro = f"RedGest inacessível ({type(exc).__name__})"
            db.commit()
            raise _indisponivel("renovação", exc) from exc
        if resp.status_code in (401, 403):
            lic.status = STATUS_REVOGADA
            lic.ultima_tentativa_em = _agora()
            lic.ultimo_erro = "revogada pelo RedGest"
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
    lic.token_jwt = _campo(dados, "access_token", "renovação")
    lic.token_expira_em = agora + dt.timedelta(
        seconds=int(_campo(dados, "expires_in", "renovação"))
    )
    lic.tolerancia_expira_em = _janela_tolerancia(lic.token_expira_em)
    lic.ultima_validacao = agora
    lic.ultima_tentativa_em = agora
    lic.ultimo_erro = None
    lic.entitlements = {
        "cnpj_vinculado": dados.get("cnpj_vinculado"),
        "max_estacoes": dados.get("max_estacoes"),
        "modulos_habilitados": dados.get("modulos_habilitados") or [],
    }
    db.commit()
    db.refresh(lic)
    _recalcular_estado(lic)
    return situacao(db)


def _atraso_proximo_ciclo(falhas: int) -> int:
    """Espera até o próximo ciclo: normal sem falhas; backoff crescente com falhas.

    Backoff (1/5/15 min por padrão) evita bater no RedGest a cada ciclo quando
    ele está fora, mas volta ao intervalo normal assim que uma renovação dá
    certo.
    """
    if falhas <= 0:
        return settings.licenca_refresh_intervalo_segundos
    backoff = settings.licenca_backoff
    indice = min(falhas - 1, len(backoff) - 1)
    return backoff[indice]


def _tentativa_renovacao() -> bool:
    """Uma passada do loop. Devolve `True` quando houve falha de renovação.

    Falha de rede agora vira `HTTPException(503)` dentro de `renovar`, então
    cai no mesmo `except HTTPException` — sem marcar revogação.
    """
    db = SessionLocal()
    try:
        lic = _licenca_local(db)
        if lic is None or lic.status != STATUS_ATIVA or lic.token_expira_em is None:
            _recalcular_estado(lic)
            return False
        faltando = (lic.token_expira_em - _agora()).total_seconds()
        _recalcular_estado(lic)
        if faltando > settings.licenca_renova_antes_segundos:
            return False
        try:
            renovar(db)
            return False
        except HTTPException:
            _recalcular_estado(lic)
            return True
    finally:
        db.close()


async def loop_renovacao() -> None:
    falhas = 0
    while True:
        if not _desabilitada():
            try:
                falhou = await asyncio.to_thread(_tentativa_renovacao)
            except Exception:  # noqa: BLE001 — falha externa não derruba o loop
                logger.exception("Falha inesperada na renovação automática da licença.")
                falhou = True
            falhas = falhas + 1 if falhou else 0
        await asyncio.sleep(_atraso_proximo_ciclo(falhas))