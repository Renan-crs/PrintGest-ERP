#!/usr/bin/env python
"""RedGest Stub — servidor local de licenciamento para o modelo `online_periodic`.

Espelha o contrato genérico do RedGest (plano de generalização aprovado) que o
PrintGest deverá consumir em produção. Endpoints por licença:

  POST /api/v1/sistemas/                    registra/atualiza um sistema (dev)
  GET  /api/v1/sistemas/{codigo}            consulta o sistema + chave pública
  POST /api/v1/licencas/                    cria licença (idempotente) -> licenca_id
  POST /api/v1/licencas/{id}/ativar         ativação inicial (CNPJ + código) -> credenciais + JWT
  POST /api/v1/licencas/{id}/validar        validação periódica (pull) -> novo JWT
  POST /api/v1/licencas/{id}/revogar        revoga (simula inadimplência/cancelamento)
  GET  /api/v1/licencas/{id}                status da licença (dev)
  GET  /api/v1/licencas/{id}/eventos        trilha append-only (webhook pré-evento)
  GET  /api/v1/health                       status do stub

Características:
- `tipo_licenciamento: online_periodic`: licença por CNPJ (sem hardware ID); o
  JWT é de curta duração (default 4h), renovado com TTL configurável via env
  `REDGEST_STUB_TOKEN_TTL` (em segundos) para acelerar testes de modo leitura.
- JWT assinado em RS256 com par de chaves gerado uma vez e persistido em
  `.dev/redgest_stub_jwt/` (a chave pública é exposta em /sistemas/{codigo}).
- Licenças válidas (dev): ver SEED_CNPJ / SEED_CODIGO_LICENCA. Para simular
  revogação, remova o código do seed ou altere o client_secret derivado.
- Estados: `aguardando` -> `ativa` -> `revogada`. Webhooks do plano (§4) não são
  entregues (rede local não recebe push); ficam registrados como eventos e o
  cliente deve usar polling em `/validar` — modelo já previsto no PRD §3.2.6.

Uso:
  <backend venv>/python -m uvicorn scripts.redgest_stub:app --host 127.0.0.1 --port 9100
"""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

SISTEMA = "grafica_erp"
TIPO_LICENCIAMENTO = "online_periodic"
STATUS_AGUARDANDO = "aguardando"
STATUS_ATIVA = "ativa"
STATUS_REVOGADA = "revogada"

SEED_CNPJ = "00000000000191"
SEED_CODIGO_LICENCA = "TESTE-GRAFICA-2026"
SEED_PLANO = "mensal"
SEED_MAX_ESTACOES = 5
SEED_MODULOS = ["cadastros", "movimento", "estoque", "financeiro", "fiscal", "relatorios"]

TOKEN_TTL_SECONDS = int(os.environ.get("REDGEST_STUB_TOKEN_TTL", str(4 * 60 * 60)))

# --- Catálogo genérico de sistemas (plano §2.1, tipo `Sistema`) -----------------
SISTEMAS: dict[str, dict[str, Any]] = {
    SISTEMA: {
        "codigo": SISTEMA,
        "nome_exibicao": "ERP Gráfica Rápida",
        "tipo_licenciamento": TIPO_LICENCIAMENTO,
        "schema_entitlements": {
            "cnpj_vinculado": "string",
            "max_estacoes": "integer",
            "modulos_habilitados": "list[string]",
        },
        "planos": ["mensal", "anual"],
        "webhook_url": None,
    }
}

# --- Licenças e eventos em memória (dev) -----------------------------------------
LICENCAS: dict[str, dict[str, Any]] = {}
EVENTOS: dict[str, list[dict[str, Any]]] = {}

# --- Chave RS256 de dev ---------------------------------------------------------
_KEY_DIR = Path(__file__).resolve().parent.parent / ".dev" / "redgest_stub_jwt"
_PRIVATE_PEM = _KEY_DIR / "jwt_rs256.pem"


def _carregar_ou_gerar_chave() -> RSAPrivateKey:
    if _PRIVATE_PEM.exists():
        return serialization.load_pem_private_key(_PRIVATE_PEM.read_bytes(), password=None)
    _KEY_DIR.mkdir(parents=True, exist_ok=True)
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _PRIVATE_PEM.write_bytes(
        chave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return chave


_CHAVE = _carregar_ou_gerar_chave()


def _pem_publica() -> str:
    return _CHAVE.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


# --- JWT RS256 (stdlib + cryptography) -------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _assinar_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": "RS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    assinatura = _CHAVE.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(assinatura)}"


def _payload_token(client_id: str, licenca: dict[str, Any], agora: int, expira: int) -> dict[str, Any]:
    return {
        "iss": "redgest-stub",
        "sub": client_id,
        "jti": uuid.uuid4().hex,
        "sistema": licenca["sistema"],
        "tipo": TIPO_LICENCIAMENTO,
        "cnpj_vinculado": licenca["cnpj"],
        "max_estacoes": licenca["max_estacoes"],
        "modulos_habilitados": licenca["modulos"],
        "iat": agora,
        "exp": expira,
    }


def _emitir_token(licenca: dict[str, Any]) -> dict[str, Any]:
    agora = int(time.time())
    expira = agora + TOKEN_TTL_SECONDS
    licenca["token"] = _assinar_jwt(_payload_token(licenca["client_id"], licenca, agora, expira))
    licenca["token_expira_em"] = expira
    return {
        "access_token": licenca["token"],
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SECONDS,
    }


def _evento(licenca_id: str, tipo: str, detalhe: str | None = None) -> None:
    EVENTOS.setdefault(licenca_id, []).append(
        {
            "tipo": tipo,
            "ocorrido_em": time.time(),
            "detalhe": detalhe,
        }
    )


# --- Credenciais determinísticas (CNPJ + código) -----------------------------------
def _client_credentials(cnpj: str, codigo: str) -> tuple[str, str]:
    seed = f"{cnpj}:{codigo}"
    return (
        f"grafica_{cnpj}",
        hashlib.sha256(seed.encode()).hexdigest()[:32],
    )


def _licenca_do_seed(cnpj: str, codigo: str) -> dict[str, Any] | None:
    if cnpj != SEED_CNPJ or codigo != SEED_CODIGO_LICENCA:
        return None
    return {
        "sistema": SISTEMA,
        "cnpj": cnpj,
        "codigo_licenca": codigo,
        "plano": SEED_PLANO,
        "max_estacoes": SEED_MAX_ESTACOES,
        "modulos": SEED_MODULOS,
    }


def _licenca_por_id(licenca_id: str) -> dict[str, Any]:
    licenca = LICENCAS.get(licenca_id)
    if not licenca:
        raise HTTPException(status_code=404, detail="Licença não encontrada.")
    return licenca


def _check_credentials(licenca: dict[str, Any], client_id: str, client_secret: str) -> None:
    if licenca.get("client_id") != client_id or not hmac.compare_digest(
        client_secret, licenca.get("client_secret", "")
    ):
        raise HTTPException(status_code=401, detail="Credenciais inválidas (revogadas?).")


# --- Esquemas de entrada -----------------------------------------------------------
class SistemaIn(BaseModel):
    codigo: str
    nome_exibicao: str
    tipo_licenciamento: str
    schema_entitlements: dict[str, Any]
    planos: list[str] = []
    webhook_url: str | None = None


class LicencaCreateIn(BaseModel):
    sistema: str
    cnpj: str
    codigo_licenca: str
    plano: str | None = None


class LicencaCredenciaisIn(BaseModel):
    client_id: str
    client_secret: str


app = FastAPI(title="RedGest Stub", version="0.2.0")


@app.post("/api/v1/sistemas")
def criar_sistema(body: SistemaIn) -> dict[str, Any]:
    if body.tipo_licenciamento not in {"online_periodic", "hardware_bound", "tenant_saas", "assinatura_simples"}:
        raise HTTPException(status_code=422, detail="tipo_licenciamento desconhecido.")
    SISTEMAS[body.codigo] = body.model_dump()
    return {"data": SISTEMAS[body.codigo]}


@app.get("/api/v1/sistemas/{codigo}")
def consultar_sistema(codigo: str) -> dict[str, Any]:
    sistema = SISTEMAS.get(codigo)
    if not sistema:
        raise HTTPException(status_code=404, detail="Sistema não cadastrado.")
    return {"data": {**sistema, "chave_publica_pem": _pem_publica()}}


@app.post("/api/v1/licencas")
def criar_licenca(body: LicencaCreateIn) -> dict[str, Any]:
    if body.sistema not in SISTEMAS:
        raise HTTPException(status_code=422, detail="Sistema não cadastrado.")
    licenca = next(
        (
            l
            for l in LICENCAS.values()
            if l["sistema"] == body.sistema and l["cnpj"] == body.cnpj and l["codigo_licenca"] == body.codigo_licenca
        ),
        None,
    )
    if licenca:
        return {"data": {"licenca_id": licenca["id"], "status": licenca["status"]}}
    licenca_id = uuid.uuid4().hex[:12]
    LICENCAS[licenca_id] = {
        "id": licenca_id,
        "sistema": body.sistema,
        "cnpj": body.cnpj,
        "codigo_licenca": body.codigo_licenca,
        "plano": body.plano or "mensal",
        "status": STATUS_AGUARDANDO,
        "max_estacoes": 0,
        "modulos": [],
        "client_id": None,
        "client_secret": None,
        "data_inicio": None,
        "token": None,
        "token_expira_em": None,
        "criado_em": time.time(),
    }
    _evento(licenca_id, "licenca.criada", body.cnpj)
    return {"data": {"licenca_id": licenca_id, "status": STATUS_AGUARDANDO}}


@app.post("/api/v1/licencas/{licenca_id}/ativar")
def ativar_licenca(licenca_id: str) -> dict[str, Any]:
    licenca = _licenca_por_id(licenca_id)
    seed = _licenca_do_seed(licenca["cnpj"], licenca["codigo_licenca"])
    if not seed:
        raise HTTPException(
            status_code=401, detail="CNPJ ou código de licença inválido para este sistema."
        )
    if licenca["status"] == STATUS_REVOGADA:
        raise HTTPException(status_code=403, detail="Licença revogada, sem reativação.")
    licenca["status"] = STATUS_ATIVA
    licenca["plano"] = seed["plano"]
    licenca["max_estacoes"] = seed["max_estacoes"]
    licenca["modulos"] = seed["modulos"]
    licenca["data_inicio"] = time.time()
    client_id, client_secret = _client_credentials(licenca["cnpj"], licenca["codigo_licenca"])
    licenca["client_id"] = client_id
    licenca["client_secret"] = client_secret
    _evento(licenca_id, "licenca.ativada", client_id)
    return {
        "data": {
            "licenca_id": licenca_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "sistema": licenca["sistema"],
            "tipo_licenciamento": TIPO_LICENCIAMENTO,
            **_emitir_token(licenca),
        }
    }


@app.post("/api/v1/licencas/{licenca_id}/validar")
def validar_licenca(licenca_id: str, body: LicencaCredenciaisIn) -> dict[str, Any]:
    licenca = _licenca_por_id(licenca_id)
    _check_credentials(licenca, body.client_id, body.client_secret)
    if licenca["status"] == STATUS_REVOGADA:
        raise HTTPException(status_code=403, detail="Licença revogada — não autorizada.")
    if licenca["status"] != STATUS_ATIVA:
        raise HTTPException(status_code=400, detail="Licença ainda não ativada.")
    _evento(licenca_id, "licenca.renovada", None)
    return {
        "data": {
            "sistema": licenca["sistema"],
            "tipo_licenciamento": TIPO_LICENCIAMENTO,
            "cnpj_vinculado": licenca["cnpj"],
            "max_estacoes": licenca["max_estacoes"],
            "modulos_habilitados": licenca["modulos"],
            **_emitir_token(licenca),
        }
    }


@app.post("/api/v1/licencas/{licenca_id}/revogar")
def revogar_licenca(licenca_id: str, body: LicencaCredenciaisIn) -> dict[str, Any]:
    licenca = _licenca_por_id(licenca_id)
    _check_credentials(licenca, body.client_id, body.client_secret)
    licenca["status"] = STATUS_REVOGADA
    _evento(licenca_id, "licenca.revogada", body.client_id)
    return {"data": {"licenca_id": licenca_id, "status": STATUS_REVOGADA}}


@app.get("/api/v1/licencas/{licenca_id}")
def status_licenca(licenca_id: str) -> dict[str, Any]:
    licenca = _licenca_por_id(licenca_id)
    return {
        "data": {
            "licenca_id": licenca_id,
            "sistema": licenca["sistema"],
            "cnpj": licenca["cnpj"],
            "plano": licenca["plano"],
            "status": licenca["status"],
            "max_estacoes": licenca["max_estacoes"],
            "modulos_habilitados": licenca["modulos"],
            "data_inicio": licenca["data_inicio"],
            "token_expira_em": licenca["token_expira_em"],
        }
    }


@app.get("/api/v1/licencas/{licenca_id}/eventos")
def eventos_licenca(licenca_id: str) -> dict[str, Any]:
    _licenca_por_id(licenca_id)
    return {"data": EVENTOS.get(licenca_id, [])}


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "sistema": SISTEMA,
        "tipo_licenciamento": TIPO_LICENCIAMENTO,
    }


if __name__ == "__main__":
    import uvicorn

    # reload=True quebra no Windows (uvicorn usa multiprocessing spawn e o
    # subprocesso não reexecuta o script de forma confiável). Para recarregamento,
    # use: uvicorn scripts.redgest_stub:app --port 9100 --reload
    uvicorn.run("scripts.redgest_stub:app", host="127.0.0.1", port=9100, reload=False)