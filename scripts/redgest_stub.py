#!/usr/bin/env python
"""
RedGest Stub — servidor local para desenvolvimento/teste do modelo
`online_periodic` (PRD v2.0 §3.4), enquanto o time do RedGest não
homologa o tipo de licenciamento.

Endpoint contratuais (espelham o GDD do RedGest):
  POST /v1/ativacao   {cnpj, codigo_licenca}            -> {client_id, client_secret}
  POST /v1/token      {client_id, client_secret}        -> {access_token, expires_in, ...}
  GET  /v1/health                                       -> status do stub

Uso:
  uvicorn scripts.redgest_stub:app --port 9100

Licenças conhecidas (dev): ver LICENCAS_CONFIG. Para simular revogação,
remova o código da lista ou altere o secret do client_id.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SISTEMA = "grafica_erp"
TIPO_LICENCIAMENTO = "online_periodic"
TOKEN_TTL_SECONDS = 4 * 60 * 60  # 4h — janela de tolerância offline (24–72h)

# CNPJ -> códigos de licença válidos (dev)
LICENCAS_CONFIG: dict[str, dict[str, str]] = {
    "00000000000191": {"codigo_licenca": "TESTE-GRAFICA-2026", "max_estacoes": "5"},
}


# --- utilidades JWT HS256 (stdlib apenas, sem dependência PyJWT) -------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign_payload(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _client_credentials(cnpj: str, codigo: str) -> tuple[str, str]:
    """client_id/client_secret derivados do CNPJ — determinístico, sem armazenamento."""
    seed = f"{cnpj}:{codigo}"
    return (
        f"grafica_{cnpj}",
        hashlib.sha256(seed.encode()).hexdigest()[:32],
    )


# --- esquema de entrada ------------------------------------------------------
class AtivacaoIn(BaseModel):
    cnpj: str
    codigo_licenca: str


class TokenIn(BaseModel):
    client_id: str
    client_secret: str


app = FastAPI(title="RedGest Stub", version="0.1.0")


@app.post("/v1/ativacao")
def ativacao(body: AtivacaoIn) -> dict[str, str]:
    licenca = LICENCAS_CONFIG.get(body.cnpj)
    if not licenca or licenca["codigo_licenca"] != body.codigo_licenca:
        raise HTTPException(status_code=401, detail="CNPJ ou código de licença inválido")
    client_id, client_secret = _client_credentials(body.cnpj, body.codigo_licenca)
    return {
        "sistema": SISTEMA,
        "tipo_licenciamento": TIPO_LICENCIAMENTO,
        "client_id": client_id,
        "client_secret": client_secret,
    }


@app.post("/v1/token")
def token(body: TokenIn) -> dict[str, Any]:
    licenca = next(
        (c for cnpj, c in LICENCAS_CONFIG.items() if _client_credentials(cnpj, c["codigo_licenca"])[0] == body.client_id),
        None,
    )
    if not licenca:
        raise HTTPException(status_code=401, detail="client_id desconhecido")

    client_id, client_secret = _client_credentials(
        next(k for k, v in LICENCAS_CONFIG.items() if v["codigo_licenca"] == licenca["codigo_licenca"]),
        licenca["codigo_licenca"],
    )
    if not hmac.compare_digest(body.client_secret, client_secret):
        raise HTTPException(status_code=401, detail="client_secret inválido (revogado?)")

    now = int(time.time())
    cnpj_vinculado = next(k for k, v in LICENCAS_CONFIG.items() if v["codigo_licenca"] == licenca["codigo_licenca"])
    payload = {
        "iss": "redgest-stub",
        "sub": body.client_id,
        "sistema": SISTEMA,
        "tipo": TIPO_LICENCIAMENTO,
        "cnpj_vinculado": cnpj_vinculado,
        "max_estacoes": int(licenca["max_estacoes"]),
        "modulos_habilitados": [
            "cadastros",
            "movimento",
            "estoque",
            "financeiro",
            "fiscal",
            "relatorios",
        ],
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    access_token = _sign_payload(payload, client_secret)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
    }


@app.get("/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "sistema": SISTEMA,
        "tipo_licenciamento": TIPO_LICENCIAMENTO,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("scripts.redgest_stub:app", host="127.0.0.1", port=9100, reload=True)