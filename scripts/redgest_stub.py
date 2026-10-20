#!/usr/bin/env python
"""RedGest Stub — servidor local de licenciamento para o PrintGest.

Dois contratos são servidos, um por família de rotas:

**Contrato C (vigente, §8 do manual)** — chave de produto validada online,
autenticada por HMAC do `Sistema.api_key`:

  POST /api/v1/licencas-software/validar/   valida a chave + fingerprint (HMAC)

**Contrato B (RedGest v4.x, §7 do manual — `docs/migracao_redgest_v4.md`)** —
`/api/v1/licencas/` com `strategia_validacao` configurável. Em dev o stub roda
`hardware_bound` (a estratégia escolhida para o PrintGest), cujo `/validar` exige
`hardware_profile` vinculado; o handshake por CNPJ + código do §7.2 é exclusivo de
`online_periodic`, então aqui ele é servido com o mesmo formato para o produto
poder ser exercitado de ponta a ponta (`REDGEST_STUB_ESTRATEGIA=hardware_bound`):

  POST /api/v1/sistemas/                     registra/atualiza um sistema (dev)
  GET  /api/v1/sistemas/{codigo}             consulta o sistema + chave pública
  POST /api/v1/licencas/                     cria licença (idempotente)
  POST /api/v1/licencas/{codigo}/ativar/     handshake -> credenciais + vigência
  POST /api/v1/licencas/{codigo}/validar/    revalida (credenciais + hardware)
  POST /api/v1/licencas/{codigo}/revogar/    revoga (simula inadimplência)
  GET  /api/v1/licencas/{codigo}             situação da licença (dev)
  GET  /api/v1/licencas/{codigo}/eventos     auditoria das chamadas (dev)
  GET  /api/v1/health                        status do stub

Chaves de produto de teste (Contrato C):
- válida:    `REDGEST_STUB_CHAVE` (default `A3F1-9C2B-77DE-1045`)
- revogada:  `0000-0000-0000-0000`
- bloqueada: `1111-1111-1111-1111`
- expirada:  `2222-2222-2222-2222`
- vitalícia: `3333-3333-3333-3333`

Códigos de licença de teste (Contrato B — todos com CNPJ `SEED_CNPJ`):
- `TESTE-GRAFICA-2026`      ativa, vence em 1 ano (o PrintGest usa este CNPJ)
- `EXPIRADA-GRAFICA-2026`   venceu há 1 dia  -> `valida=false, licenca_expirada`
                            com `grace_deadline` ainda futuro (tolerância)
- `VENCIDA-GRAFICA-2026`    venceu há 10 dias -> grace esgotado (modo leitura)
- `SUSPENSA-GRAFICA-2026`   suspensa          -> `licenca_suspensa`
- `BLOQUEADA-GRAFICA-2026`  bloqueada         -> `licenca_bloqueada`
- `REVOGADA-GRAFICA-2026`   revogada          -> `licenca_revogada`
- `HARDWARE-2026`           vinculada a outra máquina -> `hardware_divergente`
- `VITALICIA-GRAFICA-2026`  sem `data_fim` (vigência eterna)

O segredo HMAC é `REDGEST_STUB_API_KEY` (default `chave-api-printgest-dev`) e
precisa casar com `PRINTGEST_REDGEST_API_KEY` no PrintGest.

Uso:
  <backend venv>/python -m uvicorn scripts.redgest_stub:app --host 127.0.0.1 --port 9100
"""
import base64
import datetime as dt
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
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

SISTEMA = "printgest"
TIPO_LICENCIAMENTO = "hardware_bound"
STATUS_AGUARDANDO = "aguardando"
STATUS_ATIVA = "ativa"
STATUS_SUSPENSA = "suspensa"
STATUS_BLOQUEADA = "bloqueada"
STATUS_REVOGADA = "revogada"

SEED_CNPJ = "00000000000191"
SEED_CODIGO_LICENCA = "TESTE-GRAFICA-2026"
SEED_MAX_ESTACOES = 5
SEED_MODULOS = ["cadastros", "movimento", "estoque", "financeiro", "fiscal", "relatorios"]

DIA = 24 * 3600
# Tolerância do `hardware_bound` (§11.4/§12): `grace_deadline` = data_fim + 72 h.
GRACE_HORAS = int(os.environ.get("REDGEST_STUB_GRACE_HORAS", "72"))
TOKEN_TTL_SECONDS = int(os.environ.get("REDGEST_STUB_TOKEN_TTL", str(4 * 60 * 60)))
# O /validar rotaciona o `client_secret`; o anterior vale por esta janela, para
# cobrir o reenvio da mesma requisição (queda de rede entre resposta e gravação).
ROTACAO_GRACA_SEGUNDOS = int(os.environ.get("REDGEST_STUB_ROTACAO_GRACA", "300"))

MOTIVO_REVOGADA = "licenca_revogada"
MOTIVO_BLOQUEADA = "licenca_bloqueada"
MOTIVO_SUSPENSA = "licenca_suspensa"
MOTIVO_EXPIRADA = "licenca_expirada"
MOTIVO_NAO_ATIVADA = "licenca_nao_ativada"
MOTIVO_HARDWARE_DIVERGENTE = "hardware_divergente"

# --- Catálogo genérico de sistemas (plano §2.1, tipo `Sistema`) -----------------
SISTEMAS: dict[str, dict[str, Any]] = {
    SISTEMA: {
        "codigo": SISTEMA,
        "nome_exibicao": "PrintGest ERP",
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


def _epoch(agora: float, deslocamento: float | None) -> float | None:
    return agora + deslocamento if deslocamento is not None else None


def _iso(momento: float | None) -> str | None:
    if momento is None:
        return None
    return dt.datetime.fromtimestamp(momento, dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _entitlements(max_estacoes: int = SEED_MAX_ESTACOES) -> dict[str, Any]:
    return {
        "cnpj_vinculado": SEED_CNPJ,
        "max_estacoes": max_estacoes,
        "modulos_habilitados": list(SEED_MODULOS),
    }


def _nova_licenca(
    codigo: str,
    *,
    status: str = STATUS_AGUARDANDO,
    dias_fim: float | None = 365,
    cnpj: str = SEED_CNPJ,
    hardware_fixo: dict[str, str] | None = None,
) -> dict[str, Any]:
    agora = time.time()
    return {
        "id": codigo,
        "sistema": SISTEMA,
        "cnpj": cnpj,
        "codigo_licenca": codigo,
        "status": status,
        "entitlements": _entitlements(),
        "data_inicio": agora if status == STATUS_ATIVA else None,
        "data_fim": _epoch(agora, dias_fim * DIA if dias_fim is not None else None),
        "client_id": None,
        "client_secret": None,
        "secret_anterior": None,
        "secret_anterior_em": None,
        "hardware_sha256": _hash_perfil(hardware_fixo) if hardware_fixo else None,
        "ativacoes": 0,
        "ultima_validacao": None,
        "criado_em": agora,
    }


def _semeiar_licencas() -> None:
    """Matriz de cenários do Contrato B (id == código de licença, §7)."""
    semeadas = {
        SEED_CODIGO_LICENCA: {},
        "EXPIRADA-GRAFICA-2026": {"dias_fim": -1},
        "VENCIDA-GRAFICA-2026": {"dias_fim": -10},
        "SUSPENSA-GRAFICA-2026": {"status": STATUS_SUSPENSA},
        "BLOQUEADA-GRAFICA-2026": {"status": STATUS_BLOQUEADA},
        "REVOGADA-GRAFICA-2026": {"status": STATUS_REVOGADA},
        "HARDWARE-2026": {"hardware_fixo": {"cpu": "outra-maquina", "placa_mae": "0"}},
        "VITALICIA-GRAFICA-2026": {"dias_fim": None},
    }
    for codigo, campos in semeadas.items():
        # Sementes já estão vigentes: só o `criar_licenca` nasce `aguardando`.
        opcoes = {"status": STATUS_ATIVA, **campos}
        LICENCAS.setdefault(codigo, _nova_licenca(codigo, **opcoes))


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


def _token_b(licenca: dict[str, Any]) -> tuple[str, int, int]:
    """JWT `licenciamento` do §7.4 (`token`, `token_expira_em`, `expires_in`)."""
    agora = int(time.time())
    expira = agora + TOKEN_TTL_SECONDS
    payload = {
        "iss": "redgest-stub",
        "sub": licenca["client_id"],
        "jti": uuid.uuid4().hex,
        "sistema": licenca["sistema"],
        "tipo": "licenciamento",
        "cnpj_vinculado": licenca["cnpj"],
        "max_estacoes": licenca["entitlements"].get("max_estacoes"),
        "modulos_habilitados": licenca["entitlements"].get("modulos_habilitados"),
        "iat": agora,
        "exp": expira,
    }
    return _assinar_jwt(payload), expira, TOKEN_TTL_SECONDS


def _evento(licenca_id: str, tipo: str, detalhe: str | None = None) -> None:
    EVENTOS.setdefault(licenca_id, []).append(
        {
            "tipo": tipo,
            "ocorrido_em": time.time(),
            "detalhe": detalhe,
        }
    )


# --- Credenciais determinísticas (CNPJ + código) -----------------------------------
def _credenciais(cnpj: str, codigo: str) -> tuple[str, str]:
    """Par emitido no handshake. `client_secret` de 32 caracteres (hash hex)."""
    seed = f"{cnpj}:{codigo}"
    return (
        f"grafica_{cnpj}",
        hashlib.sha256(seed.encode()).hexdigest()[:32],
    )


def _secret_aceito(licenca: dict[str, Any], candidato: str) -> bool:
    """Secret vigente ou o anterior ainda dentro da tolerância de reenvio (§7.3).

    A rotação emite um novo `client_secret` a cada `/validar`; uma requisição
    reenviada (queda de rede entre a resposta e a gravação) carrega o secret
    antigo e precisa continuar válida durante essa tolerância.
    """
    candidatos = [licenca.get("client_secret")]
    if (
        licenca.get("secret_anterior") is not None
        and licenca.get("secret_anterior_em") is not None
        and time.time() - licenca["secret_anterior_em"] <= ROTACAO_GRACA_SEGUNDOS
    ):
        candidatos.append(licenca["secret_anterior"])
    return any(
        hmac.compare_digest(candidato, vigente)
        for vigente in candidatos
        if vigente
    )


def _hash_perfil(perfil: dict[str, Any]) -> str:
    """SHA-256 do JSON canônico (chaves ordenadas) — mesmo cálculo do RedGest."""
    canonico = json.dumps(perfil, sort_keys=True, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _grace_deadline(licenca: dict[str, Any]) -> float | None:
    fim = licenca.get("data_fim")
    return fim + GRACE_HORAS * 3600 if fim else None


def _dias_restantes(licenca: dict[str, Any]) -> int | None:
    fim = licenca.get("data_fim")
    return int((fim - time.time()) // DIA) if fim else None


def _licenca_por_id(licenca_id: str) -> dict[str, Any] | None:
    return LICENCAS.get(licenca_id)


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


class AtivarIn(BaseModel):
    cnpj: str
    codigo_licenca: str

class ValidarIn(BaseModel):
    client_id: str
    client_secret: str
    hardware_profile: dict[str, Any] | None = None
    ip_origem: str | None = None
    usuario: str | None = None
    contexto: dict[str, Any] | None = None


class CredenciaisIn(BaseModel):
    client_id: str
    client_secret: str


app = FastAPI(title="RedGest Stub", version="1.0.0")


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
    """Cria/atualiza uma licença pelo código (idempotente — backoffice em dev)."""
    if body.sistema not in SISTEMAS:
        raise HTTPException(status_code=422, detail="Sistema não cadastrado.")
    codigo = body.codigo_licenca.strip().upper()
    licenca = LICENCAS.get(codigo)
    if licenca is None:
        licenca = _nova_licenca(codigo, status=STATUS_AGUARDANDO, dias_fim=None, cnpj=body.cnpj)
        LICENCAS[codigo] = licenca
        _evento(codigo, "licenca.criada", body.cnpj)
    return {"data": {"id": licenca["id"], "status": licenca["status"]}}


@app.post("/api/v1/licencas/{licenca_id}/ativar/")
def ativar_licenca(licenca_id: str, body: AtivarIn, request: Request):
    """Handshake do Contrato B (§7.2): credenciais + vigência, uma única vez."""
    if not request.headers.get("Idempotency-Key"):
        return _erro_chave(
            400, "Header Idempotency-Key obrigatório.", "IDEMPOTENCY_KEY_OBRIGATORIA"
        )
    licenca = _licenca_por_id(licenca_id)
    if licenca is None:
        return _erro_chave(404, "Licença não encontrada.", "LICENCA_NAO_ENCONTRADA")
    if licenca["cnpj"] != body.cnpj or licenca["codigo_licenca"] != body.codigo_licenca:
        # §14.1 cenário 2: CNPJ/codigo que nao conferem -> 400, como no RedGest.
        return _erro_chave(
            400,
            "CNPJ ou codigo de licenca nao conferem.",
            "CNPJ_NAO_CONFERE",
        )
    if licenca["status"] == STATUS_REVOGADA:
        return _erro_chave(400, "Licença revogada, sem reativação.", "LICENCA_REVOGADA")
    if licenca["status"] != STATUS_ATIVA:
        return _erro_chave(
            400,
            f"Licença {licenca['status']}, sem reativação.",
            f"LICENCA_{licenca['status'].upper()}",
        )
    if licenca["data_fim"] is not None and licenca["data_fim"] <= time.time():
        return _erro_chave(400, "Licença expirada, sem reativação.", "LICENCA_EXPIRADA")

    if licenca["client_id"] is None:
        licenca["client_id"], licenca["client_secret"] = _credenciais(
            licenca["cnpj"], licenca["codigo_licenca"]
        )
        licenca["data_inicio"] = licenca["data_inicio"] or time.time()
        _evento(licenca_id, "licenca.ativada", licenca["client_id"])
    else:
        # Reativação idempotente: devolve o mesmo par emitido na primeira vez.
        _evento(licenca_id, "licenca.reativada", licenca["client_id"])

    return JSONResponse(
        content={
            "data": {
                "id": licenca_id,
                "cliente_id": licenca["cnpj"],
                "sistema_codigo": licenca["sistema"],
                "status": licenca["status"],
                "entitlements": licenca["entitlements"],
                "data_inicio": _iso(licenca["data_inicio"]),
                "data_fim": _iso(licenca["data_fim"]),
                "client_id": licenca["client_id"],
                "client_secret": licenca["client_secret"],
                "modo": "on_premise",
            }
        }
    )


@app.post("/api/v1/licencas/{licenca_id}/validar/")
def validar_licenca(licenca_id: str, body: ValidarIn, request: Request):
    """Revalidação periódica (§7.3): credenciais + `hardware_profile`."""
    if not request.headers.get("Idempotency-Key"):
        return _erro_chave(
            400, "Header Idempotency-Key obrigatório.", "IDEMPOTENCY_KEY_OBRIGATORIA"
        )
    licenca = _licenca_por_id(licenca_id)
    if licenca is None:
        return _erro_chave(404, "Licença não encontrada.", "LICENCA_NAO_ENCONTRADA")
    if licenca.get("client_id") != body.client_id or not _secret_aceito(
        licenca, body.client_secret
    ):
        return _erro_chave(403, "Credenciais inválidas.", "CREDENCIAIS_INVALIDAS")

    agora = time.time()
    motivo = ""
    valida = True
    if licenca["status"] == STATUS_REVOGADA:
        valida, motivo = False, MOTIVO_REVOGADA
    elif licenca["status"] == STATUS_BLOQUEADA:
        valida, motivo = False, MOTIVO_BLOQUEADA
    elif licenca["status"] == STATUS_SUSPENSA:
        valida, motivo = False, MOTIVO_SUSPENSA
    elif licenca["status"] != STATUS_ATIVA:
        valida, motivo = False, MOTIVO_NAO_ATIVADA
    elif licenca["data_fim"] is not None and licenca["data_fim"] <= agora:
        valida, motivo = False, MOTIVO_EXPIRADA

    perfil = body.hardware_profile or {}
    if valida and perfil:
        digest = _hash_perfil(perfil)
        vinculado = licenca["hardware_sha256"]
        if vinculado is None:
            licenca["hardware_sha256"] = digest  # bind na primeira validação (§11.4)
            _evento(licenca_id, "hardware.vinculado", digest[:12])
        elif not hmac.compare_digest(digest, vinculado):
            valida, motivo = False, MOTIVO_HARDWARE_DIVERGENTE

    token = None
    token_expira_em = None
    expires_in = None
    if valida:
        token, token_expira_em, expires_in = _token_b(licenca)
        # §7.3: o /validar emite um novo secret e o anterior deixa de valer.
        licenca["secret_anterior"] = licenca["client_secret"]
        licenca["secret_anterior_em"] = agora
        licenca["client_secret"] = hashlib.sha256(
            f"{licenca['client_id']}:{uuid.uuid4().hex}".encode()
        ).hexdigest()[:32]
        licenca["ativacoes"] += 1
    licenca["ultima_validacao"] = agora
    _evento(licenca_id, "licenca.validada", motivo or "ok")

    dados: dict[str, Any] = {
        "licenca_id": licenca_id,
        "valida": valida,
        "status": STATUS_ATIVA if valida else licenca["status"],
        "motivo": motivo,
        "sistema_codigo": licenca["sistema"],
        "cliente_id": licenca["cnpj"],
        "entitlements": licenca["entitlements"],
        "dias_restantes": _dias_restantes(licenca),
        "grace_deadline": _iso(_grace_deadline(licenca)),
        "token": token,
        "token_expira_em": _iso(token_expira_em),
        "expires_in": expires_in,
        "client_id": licenca["client_id"],
    }
    if valida:
        dados["client_secret"] = licenca["client_secret"]
    return JSONResponse(content={"data": dados})


@app.post("/api/v1/licencas/{licenca_id}/revogar/")
def revogar_licenca(licenca_id: str, body: CredenciaisIn) -> dict[str, Any]:
    """Simula inadimplência (admin em dev)."""
    licenca = _licenca_por_id(licenca_id)
    if licenca is None:
        return {"data": {"licenca_id": licenca_id, "status": None}}
    if licenca["client_id"] != body.client_id:
        raise HTTPException(status_code=403, detail="Credenciais inválidas.")
    licenca["status"] = STATUS_REVOGADA
    _evento(licenca_id, "licenca.revogada", body.client_id)
    return {"data": {"licenca_id": licenca_id, "status": STATUS_REVOGADA}}


@app.get("/api/v1/licencas/{licenca_id}")
def status_licenca(licenca_id: str) -> dict[str, Any]:
    licenca = _licenca_por_id(licenca_id)
    if licenca is None:
        raise HTTPException(status_code=404, detail="Licença não encontrada.")
    return {
        "data": {
            "id": licenca["id"],
            "sistema": licenca["sistema"],
            "cnpj": licenca["cnpj"],
            "status": licenca["status"],
            "entitlements": licenca["entitlements"],
            "data_inicio": _iso(licenca["data_inicio"]),
            "data_fim": _iso(licenca["data_fim"]),
            "grace_deadline": _iso(_grace_deadline(licenca)),
            "hardware_vinculado": licenca["hardware_sha256"],
            "validacoes": licenca["ativacoes"],
            "hardware_vinculado": licenca["hardware_sha256"],
        }
    }


@app.get("/api/v1/licencas/{licenca_id}/eventos")
def eventos_licenca(licenca_id: str) -> dict[str, Any]:
    if licenca_id not in LICENCAS:
        raise HTTPException(status_code=404, detail="Licença não encontrada.")
    return {"data": EVENTOS.get(licenca_id, [])}


# --- Contrato C: chave de produto (`/licencas-software/validar/`) -----------------
API_KEY_CHAVE = os.environ.get("REDGEST_STUB_API_KEY", "chave-api-printgest-dev")
TOLERANCIA_ASSINATURA_SEGUNDOS = 300

SEED_CHAVE_ATIVACAO = os.environ.get("REDGEST_STUB_CHAVE", "A3F1-9C2B-77DE-1045")
SEED_LIMITE_ATIVACOES = 5
_SEED_EXPIRA = time.time() + 365 * 24 * 3600

# Chave -> licença fake. `expira_em=None` = vitalícia.
LICENCAS_SOFTWARE: dict[str, dict[str, Any]] = {
    SEED_CHAVE_ATIVACAO: {
        "status": "ATIVA",
        "plano": "ANUAL",
        "limite_ativacoes": SEED_LIMITE_ATIVACOES,
        "fingerprints": [],
        "expira_em": _SEED_EXPIRA,
    },
    "3333-3333-3333-3333": {  # vitalícia
        "status": "ATIVA",
        "plano": "VITALICIA",
        "limite_ativacoes": 1,
        "fingerprints": [],
        "expira_em": None,
    },
    "0000-0000-0000-0000": {
        "status": "REVOGADA",
        "plano": "ANUAL",
        "limite_ativacoes": 1,
        "fingerprints": [],
        "expira_em": _SEED_EXPIRA,
    },
    "1111-1111-1111-1111": {
        "status": "BLOQUEADA",
        "plano": "ANUAL",
        "limite_ativacoes": 1,
        "fingerprints": [],
        "expira_em": _SEED_EXPIRA,
    },
    "2222-2222-2222-2222": {
        "status": "EXPIRADA",
        "plano": "MENSAL",
        "limite_ativacoes": 1,
        "fingerprints": [],
        "expira_em": time.time() - 24 * 3600,
    },
}


def _assinatura_redgest(segredo: str, nonce: str, timestamp: str, body: bytes) -> str:
    material = f"{nonce}{timestamp}".encode("utf-8") + body
    digest = hmac.new(segredo.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _erro_chave(status_code: int, detail: str, codigo: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"detail": detail, "codigo": codigo}
    )


@app.post("/api/v1/licencas-software/validar/")
async def validar_licenca_software(request: Request) -> JSONResponse:
    """Espelha `ValidarLicencaSoftwareView` (RedGest v3.6 §8.4)."""
    # Corpo bruto lido ANTES de qualquer parse: a assinatura cobre estes bytes.
    corpo = await request.body()
    try:
        dados = json.loads(corpo.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return _erro_chave(400, "JSON inválido.", "CORPO_INVALIDO")

    chave = (dados.get("chave_ativacao") or "").strip().upper()
    fingerprint = (dados.get("maquina_fingerprint") or "").strip()
    licenca = LICENCAS_SOFTWARE.get(chave)
    if licenca is None:
        # O RedGest resolve o segredo *pela* chave: chave desconhecida cai aqui.
        return _erro_chave(
            403,
            "Sistema sem credencial de integração configurada.",
            "SISTEMA_SEM_CREDENCIAL",
        )

    nonce = request.headers.get("X-RedGest-Nonce")
    timestamp = request.headers.get("X-RedGest-Timestamp")
    assinatura = request.headers.get("X-RedGest-Signature")
    if not (nonce and timestamp and assinatura):
        return _erro_chave(
            401, "Assinatura HMAC obrigatória.", "ASSINATURA_OBRIGATORIA"
        )
    if not hmac.compare_digest(
        _assinatura_redgest(API_KEY_CHAVE, nonce, timestamp, corpo), assinatura
    ):
        return _erro_chave(401, "Assinatura inválida.", "ASSINATURA_INVALIDA")
    try:
        momento = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return _erro_chave(401, "Timestamp inválido.", "ASSINATURA_INVALIDA")
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=dt.timezone.utc)
    desvio = abs((dt.datetime.now(dt.timezone.utc) - momento).total_seconds())
    if desvio > TOLERANCIA_ASSINATURA_SEGUNDOS:
        return _erro_chave(401, "Timestamp fora da janela.", "ASSINATURA_INVALIDA")
    if not fingerprint:
        return _erro_chave(
            400, "Fingerprint da máquina obrigatório.", "FINGERPRINT_OBRIGATORIO"
        )

    if licenca["status"] == "REVOGADA":
        return _erro_chave(403, "Licença revogada.", "LICENCA_REVOGADA")
    if licenca["status"] == "BLOQUEADA":
        return _erro_chave(403, "Licença bloqueada.", "LICENCA_BLOQUEADA")
    if licenca["status"] == "EXPIRADA" or (
        licenca["expira_em"] is not None and licenca["expira_em"] <= time.time()
    ):
        licenca["status"] = "EXPIRADA"
        return _erro_chave(403, "Licença expirada.", "LICENCA_EXPIRADA")

    ja_registrada = fingerprint in licenca["fingerprints"]
    if not ja_registrada and len(licenca["fingerprints"]) >= licenca["limite_ativacoes"]:
        return _erro_chave(
            409, "Limite de ativações atingido.", "LIMITE_ATIVACOES_EXCEDIDO"
        )
    primeira = not licenca["fingerprints"]
    if not ja_registrada:
        licenca["fingerprints"].append(fingerprint)

    expira = licenca["expira_em"]
    return JSONResponse(
        content={
            "valido": True,
            "expira_em": (
                dt.datetime.fromtimestamp(expira, dt.timezone.utc).isoformat()
                if expira
                else None
            ),
            "primeira_ativacao": primeira,
            "ativacoes_realizadas": len(licenca["fingerprints"]),
            "limite_ativacoes": licenca["limite_ativacoes"],
        }
    )


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "sistema": SISTEMA,
        "tipo_licenciamento": TIPO_LICENCIAMENTO,
    }


_semeiar_licencas()


if __name__ == "__main__":
    import uvicorn

    # reload=True quebra no Windows (uvicorn usa multiprocessing spawn e o
    # subprocesso não reexecuta o script de forma confiável). Para recarregamento,
    # use: uvicorn scripts.redgest_stub:app --port 9100 --reload
    uvicorn.run("scripts.redgest_stub:app", host="127.0.0.1", port=9100, reload=False)
