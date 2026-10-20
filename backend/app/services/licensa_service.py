"""Serviço de licenciamento por chave de produto (RedGest `/licencas-software/`).

O RedGest emite uma **chave de ativação** (`XXXX-XXXX-XXXX-XXXX`, Contrato C do
manual de integração) que o usuário digita na primeira execução. Este serviço:

- **ativa**: valida a chave online em
  `POST /api/v1/licencas-software/validar/`, enviando
  `{chave_ativacao, maquina_fingerprint}` assinado por HMAC-SHA256 com a
  `api_key` do Sistema no RedGest (cabeçalhos `X-RedGest-Signature`,
  `X-RedGest-Nonce`, `X-RedGest-Timestamp`), e guarda o resultado na tabela
  local `licenca`;
- **revalida**: consulta o RedGest periodicamente (default a cada 6 h) para
  detectar revogação/bloqueio/expiração;
- **modo de leitura**: sem ativação, com a licença revogada/bloqueada/expirada
  ou com tolerância esgotada, `ESTADO["modo_leitura"]` fica `True` e o
  middleware bloqueia escritas (HTTP 423).

Resiliência (`docs/plano_resiliencia_licenca.md`): o timeout para o RedGest é
configurável (padrão 90 s, para absorver *cold start* de plano gratuito) e as
falhas de transporte viram `503` com mensagem clara — **nunca** revogação. A
licença vale até `expira_em` e, depois do vencimento, a instalação opera em
tolerância (`licenca_tolerancia_horas`, 72 h) antes de entrar em modo de leitura.
O loop aplica backoff crescente (1/5/15/60 min) com jitter entre tentativas que
falham (doc §9.2).

A **chave de ativação** fica no cofre do SO (DPAPI em escopo de máquina — doc
§9.4); `_chave_em_claro` a abre para revalidar e para mascarar na resposta. O
serial é normalizado por `_parse_chave`: a doc §4.2 manda aceitar com ou sem
hífens e validar o formato **antes** de chamar a API.

O `maquina_fingerprint` segue a doc de integração do RedGest §7: identificadores
estáveis de hardware (BIOS UUID, CPU ID, serial da placa-mãe e do disco), JSON
canônico com chaves ordenadas e SHA-256 hex. Sem eles, usa um fallback estável
(nunca hostname/MAC, que a doc manda evitar).

A assinatura segue o contrato congelado no RedGest
(`apps/liberacao/infrastructure/web/licenca_software_auth.py`):
`sha256=` + hex(HMAC_SHA256(segredo, nonce + timestamp + corpo_bruto)).
"""

import base64
import datetime as dt
import functools
import hashlib
import hmac
import json
import logging
import os
import platform
import random
import re
import subprocess
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import cofre
from app.core.config import settings
from app.db import SessionLocal
from app.models.licenca import Licenca

logger = logging.getLogger(__name__)

STATUS_ATIVA = "ativa"
STATUS_BLOQUEADA = "bloqueada"
STATUS_REVOGADA = "revogada"
STATUS_EXPIRADA = "expirada"

ESTADO_ATIVA = "ativa"
ESTADO_TOLERANCIA = "tolerancia"
ESTADO_LEITURA = "leitura"
ESTADO_REVOGADA = "revogada"
ESTADO_NAO_ATIVADA = "nao_ativada"

CAMINHO_VALIDAR = "/api/v1/licencas-software/validar/"
PREFIXO_ASSINATURA = "sha256="

# Erros de licença que chegam como 403 + `codigo` e viram estado local.
_ERROS_DE_LICENCA = {
    "LICENCA_REVOGADA": (STATUS_REVOGADA, "Licença revogada pelo RedGest."),
    "LICENCA_BLOQUEADA": (
        STATUS_BLOQUEADA,
        "Licença bloqueada pelo RedGest — regularize o contrato/pagamento.",
    ),
    "LICENCA_EXPIRADA": (STATUS_EXPIRADA, "Licença expirada no RedGest."),
}

_MSG_LIMITE = (
    "Limite de ativações desta chave atingido. Solicite a reemissão da chave ou "
    "o aumento do limite ao fornecedor."
)
_MSG_CHAVE_DESCONHECIDA = (
    "Chave de ativação não reconhecida pelo servidor de licenças. Confira a "
    "chave digitada; se estiver correta, o produto precisa estar configurado com "
    "credencial de integração no RedGest."
)

# Marca (ASCII, estável) que precede os motivos de recusa específicos do
# Contrato B em `licenca.ultimo_erro`. Só mensagens com esse prefixo são
# exibidas como motivo da licença; erros transitórios de rede ficam de fora.
_BLOQUEIO_ESPECIFICO = "[RedGest]"

ESTADO: dict[str, bool] = {"modo_leitura": not settings.licenca_desabilitada}


def _desabilitada() -> bool:
    return settings.licenca_desabilitada


def contrato_b() -> bool:
    """`True` quando a instalação fala o Contrato B (`/licencas/`, v4.0).

    A flag é lida a cada chamada (e não no import) para que a virada de contrato
    valha sem reiniciar o processo — e para a suíte poder alternar os contratos.
    """
    return (settings.redgest_contrato or "c").strip().lower() == "b"


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _cliente() -> httpx.Client:
    return httpx.Client(
        base_url=settings.redgest_url, timeout=settings.licenca_timeout_segundos
    )


def _cliente_com_idempotencia(chave_idempotencia: str) -> httpx.Client:
    """Cliente com o `Idempotency-Key` fixo de uma operação lógica (§10.1).

    O header tem de ser o **mesmo** em todas as tentativas de uma operação (a
    repetição devolve a resposta cacheada em vez de reexecutar); por isso o
    cliente é criado por operação, não por requisição.
    """
    return httpx.Client(
        base_url=settings.redgest_url,
        timeout=settings.licenca_timeout_segundos,
        headers={"Idempotency-Key": chave_idempotencia},
    )


def _correlacionar(resp: httpx.Response) -> None:
    """Loga o `X-Request-Id` do RedGest, se houver (rastreio sem vazar segredo)."""
    identificador = resp.headers.get("X-Request-Id")
    if identificador:
        logger.info("RedGest request-id: %s", identificador)


def _bloquear(
    db: Session, status_licenca: str, motivo: str, *, codigo: str = ""
) -> None:
    """Marca a licença local como não utilizável e levanta 423 com o motivo.

    O `codigo` do RedGest é guardado em `entitlements["motivo_codigo"]` para a
    UI/triagem sem depender do texto (que muda de idioma/redação).
    """
    lic = _licenca_local(db)
    if lic is not None:
        entitlements = dict(lic.entitlements or {})
        entitlements["motivo_codigo"] = codigo
        lic.entitlements = entitlements
    _marcar_status(db, status_licenca, motivo)
    raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=motivo)


def _indisponivel(contexto: str, exc: Exception) -> HTTPException:
    """Traduz falha de transporte (timeout/DNS/conexão) em 503 com mensagem clara.

    Distingue "RedGest inacessível" de "licença revogada": só a resposta
    explícita do RedGest leva ao modo de leitura; indisponibilidade de rede não.
    """
    logger.warning("RedGest inacessível (%s): %s", contexto, exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Não foi possível falar com o servidor de licenças "
            f"({contexto}). Verifique a conexão e tente novamente."
        ),
    )


def _exigir_credencial() -> None:
    if not settings.redgest_api_key:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Integração com o servidor de licenças sem credencial configurada "
                "(defina PRINTGEST_REDGEST_API_KEY)."
            ),
        )


# --------------------------------------------------------------- fingerprint
# Doc de integração RedGest §7: usar componentes estáveis (BIOS UUID, CPU ID,
# serial da placa-mãe/disco) e **evitar** hostname, usuário, IP, MAC, volume de
# disco e data de instalação.
_FINGERPRINT_VAZIOS = {
    "",
    "0",
    "none",
    "null",
    "unknown",
    "not specified",
    "default string",
    "system serial number",
    "to be filled by o.e.m.",
    "to be filled by oem",
}

_SCRIPT_HARDWARE = (
    "$out = [ordered]@{};"
    "$cs = Get-CimInstance Win32_ComputerSystemProduct -ErrorAction SilentlyContinue;"
    "if ($cs.UUID) { $out['bios_uuid'] = $cs.UUID };"
    "$bb = Get-CimInstance Win32_BaseBoard -ErrorAction SilentlyContinue;"
    "if ($bb.SerialNumber) { $out['placa_mae_serial'] = $bb.SerialNumber };"
    "$pr = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue |"
    " Select-Object -First 1;"
    "if ($pr.ProcessorId) { $out['cpu_id'] = $pr.ProcessorId };"
    "$dd = Get-CimInstance Win32_DiskDrive -ErrorAction SilentlyContinue |"
    " Sort-Object Index | Select-Object -First 1;"
    "if ($dd.SerialNumber) { $out['disco_serial'] = $dd.SerialNumber };"
    "$out | ConvertTo-Json -Compress"
)


def _valor_util(valor: Any) -> str:
    """Normaliza e descarta identificadores genéricos (doc §7.2: nunca `null`)."""
    texto = str(valor or "").strip()
    if texto.lower() in _FINGERPRINT_VAZIOS:
        return ""
    # Preenchimentos só de zeros (ex.: 00000000-0000-0000-0000-000000000000 ou
    # "0000000000") são placeholder de SMBIOS/placa, não identificador.
    if texto and set(texto) <= set("0-"):
        return ""
    return texto


def _consultar_hardware() -> dict[str, str]:
    """Identificadores estáveis de hardware do Windows (CIM); `{}` se falhar."""
    if platform.system() != "Windows":
        return {}
    try:
        saida = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _SCRIPT_HARDWARE,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        dados = json.loads(saida.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        logger.warning("Não foi possível ler os identificadores de hardware.")
        return {}
    if not isinstance(dados, dict):
        return {}
    limpos = {chave: _valor_util(valor) for chave, valor in dados.items()}
    return {chave: valor for chave, valor in limpos.items() if valor}


@functools.lru_cache(maxsize=1)
def _fingerprint_do_hardware() -> str:
    """SHA-256 do JSON canônico (chaves ordenadas) do hardware — cacheado."""
    campos = _consultar_hardware()
    if not campos:
        # Fallback estável: menos campos é melhor que campos voláteis (doc §7.2),
        # mas a requisição exige um valor — e nunca hostname/MAC.
        campos = {
            chave: valor
            for chave, valor in {
                "arquitetura": platform.machine(),
                "processador": platform.processor(),
            }.items()
            if valor
        }
    canonico = json.dumps(
        campos, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _fingerprint() -> str:
    """Fingerprint determinístico da estação (estável entre reinstalações).

    Segue a doc de integração do RedGest §7: identificadores estáveis de
    hardware, JSON canônico com chaves ordenadas e SHA-256 em hex minúsculo.
    O RedGest guarda esse valor para a cota de ativações — reenviar o mesmo
    fingerprint não consome cota nova; trocar o hardware, sim.
    """
    fixo = (settings.maquina_fingerprint or "").strip()
    if fixo:
        return fixo.lower()
    return _fingerprint_do_hardware()


# --------------------------------------------------------------- assinatura
def _corpo(chave: str, fingerprint: str) -> bytes:
    """Corpo exato (bytes) que será assinado e enviado — sem espaços."""
    return json.dumps(
        {"chave_ativacao": chave, "maquina_fingerprint": fingerprint},
        separators=(",", ":"),
    ).encode("utf-8")


def _assinatura(segredo: str, nonce: str, timestamp: str, corpo: bytes) -> str:
    material = f"{nonce}{timestamp}".encode("utf-8") + corpo
    digest = hmac.new(segredo.encode("utf-8"), material, hashlib.sha256).hexdigest()
    return f"{PREFIXO_ASSINATURA}{digest}"


def _agora_em_texto() -> str:
    return _agora().strftime("%Y-%m-%dT%H:%M:%SZ")


def _cabecalhos(corpo: bytes) -> dict:
    nonce = base64.b64encode(os.urandom(32)).decode("ascii")
    timestamp = _agora_em_texto()
    return {
        "Content-Type": "application/json",
        "X-RedGest-Signature": _assinatura(
            settings.redgest_api_key, nonce, timestamp, corpo
        ),
        "X-RedGest-Nonce": nonce,
        "X-RedGest-Timestamp": timestamp,
    }


# ------------------------------------------------------------------- parsing
def _parse_dt(valor: Any) -> dt.datetime | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, dt.datetime):
        momento = valor
    else:
        momento = dt.datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=dt.timezone.utc)
    return momento


def _corpo_json(resp: httpx.Response) -> dict:
    try:
        corpo = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta não-JSON do servidor de licenças.",
        ) from exc
    if not isinstance(corpo, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Resposta inesperada do servidor de licenças.",
        )
    # O contrato do RedGest devolve o objeto direto; aceitamos `data` por
    # compatibilidade com servidores que embrulham a resposta.
    return corpo.get("data") or corpo


def _erro_do_corpo(resp: httpx.Response) -> tuple[str | None, str]:
    codigo: str | None = None
    detalhe = "Erro relatado pelo servidor de licenças."
    try:
        corpo = resp.json()
        if isinstance(corpo, dict):
            codigo = corpo.get("codigo")
            if corpo.get("detail"):
                detalhe = str(corpo["detail"])
    except ValueError:
        pass
    return codigo, detalhe


_CHAVE_RE = re.compile(r"^[0-9A-F]{4}(-[0-9A-F]{4}){3}$")


def _parse_chave(chave: str) -> str:
    """Normaliza o serial digitado e valida o formato **antes** de chamar a API.

    A doc de integração §4.2 exige aceitar o serial com ou sem hífens (com
    espaços, colado de e-mail etc.). Limpamos tudo que não é hexadecimal,
    subimos para maiúsculas e reagrupamos em `XXXX-XXXX-XXXX-XXXX`. Devolve
    `""` quando não há exatamente 16 caracteres hexadecimais — o chamador
    responde 400 sem tocar na rede.
    """
    digitos = re.sub(r"[^0-9A-F]", "", (chave or "").upper())
    if len(digitos) != 16:
        return ""
    formatada = "-".join(digitos[i : i + 4] for i in range(0, 16, 4))
    return formatada if _CHAVE_RE.match(formatada) else ""


# -------------------------------------------------------------------- estado
def _licenca_local(db: Session) -> Licenca | None:
    return db.query(Licenca).order_by(Licenca.id).first()


@functools.lru_cache(maxsize=8)
def _abrir_chave(guardada: str) -> str:
    """Abre a chave no cofre do SO (cacheado por valor guardado)."""
    return cofre.revelar(guardada)


def _chave_em_claro(lic: Licenca | None) -> str:
    """Chave de ativação legível; `""` se não ativada ou ilegível nesta máquina."""
    if lic is None or not lic.chave_ativacao:
        return ""
    return _abrir_chave(lic.chave_ativacao)


def _janela_tolerancia(expira_em: dt.datetime) -> dt.datetime:
    return expira_em + dt.timedelta(hours=settings.licenca_tolerancia_horas)


def _tolerancia_expira_em(lic: Licenca) -> dt.datetime | None:
    """Tolerância efetiva: a coluna, ou derivada da vigência (bases anteriores)."""
    if lic.tolerancia_expira_em is not None:
        return lic.tolerancia_expira_em
    if lic.expira_em is None:
        return None
    return _janela_tolerancia(lic.expira_em)


def _estado(lic: Licenca | None) -> str:
    """Estado derivado: ativa | tolerancia | leitura | revogada | nao_ativada."""
    if not _chave_em_claro(lic):
        # Sem chave guardada ou cofre ilegível (banco de outra máquina): a
        # instalação precisa ser reativada.
        return ESTADO_NAO_ATIVADA
    if lic.status == STATUS_REVOGADA:
        return ESTADO_REVOGADA
    if lic.status in (STATUS_BLOQUEADA, STATUS_EXPIRADA):
        return ESTADO_LEITURA
    agora = _agora()
    if lic.expira_em is None or lic.expira_em > agora:
        return ESTADO_ATIVA
    tolerancia = _tolerancia_expira_em(lic)
    if tolerancia is not None and tolerancia > agora:
        return ESTADO_TOLERANCIA
    return ESTADO_LEITURA


def _modo_leitura(estado: str) -> bool:
    return estado in (ESTADO_LEITURA, ESTADO_REVOGADA, ESTADO_NAO_ATIVADA)


def _motivo(lic: Licenca | None, estado: str) -> str:
    if lic is not None and lic.status in (STATUS_BLOQUEADA, STATUS_EXPIRADA):
        # Contrato B: a recusa do RedGest (`licenca_suspensa`, `hardware_divergente`
        # etc.) fica em `ultimo_erro` e é mais específica que o texto genérico.
        especifico = (lic.ultimo_erro or "").strip()
        if especifico and _BLOQUEIO_ESPECIFICO in especifico:
            return especifico
        if lic.status == STATUS_BLOQUEADA:
            return "Licença bloqueada pelo RedGest — regularize o contrato/pagamento."
        return "Licença expirada. Renove o contrato para reativar."
    return {
        ESTADO_ATIVA: "Licença ativa.",
        ESTADO_TOLERANCIA: (
            "Vigência vencida e sem contato com o RedGest; operando em tolerância."
        ),
        ESTADO_REVOGADA: "Licença revogada pelo RedGest.",
        ESTADO_NAO_ATIVADA: "Licença ainda não ativada.",
    }.get(
        estado,
        "Tolerância esgotada: informe a chave de ativação novamente ou contate o fornecedor.",
    )


def _recalcular_estado(lic: Licenca | None) -> None:
    ESTADO["modo_leitura"] = _modo_leitura(_estado(lic))


def _mascarar(chave: str | None) -> str | None:
    if not chave:
        return None
    if len(chave) <= 4:
        return "*" * len(chave)
    return f"{'*' * (len(chave) - 4)}{chave[-4:]}"


def situacao(db: Session) -> dict:
    lic = _licenca_local(db)
    estado = _estado(lic)
    ESTADO["modo_leitura"] = _modo_leitura(estado)
    if _desabilitada():
        ESTADO["modo_leitura"] = False
    return {
        "sistema": settings.redgest_sistema,
        "contrato": "b" if contrato_b() else "c",
        "chave": _mascarar(_chave_em_claro(lic)) or None,
        "plano": lic.plano if lic else None,
        "status": lic.status if lic else ESTADO_NAO_ATIVADA,
        "estado": estado,
        "motivo": _motivo(lic, estado),
        "modo_leitura": ESTADO["modo_leitura"],
        "expira_em": lic.expira_em if lic else None,
        "tolerancia_expira_em": _tolerancia_expira_em(lic) if lic else None,
        "limite_ativacoes": lic.limite_ativacoes if lic else None,
        "ativacoes_realizadas": lic.ativacoes_realizadas if lic else None,
        "ultima_validacao": lic.ultima_validacao if lic else None,
        "ultima_tentativa_em": lic.ultima_tentativa_em if lic else None,
        "ultimo_erro": lic.ultimo_erro if lic else None,
    }


# ---------------------------------------------------------------- persistência
def _persistir_ok(
    db: Session, *, chave: str, fingerprint: str, dados: dict
) -> None:
    lic = _licenca_local(db)
    agora = _agora()
    expira = _parse_dt(dados.get("expira_em"))
    if lic is None:
        lic = Licenca()
        db.add(lic)
    # Doc §9.4: a chave de ativação vai para o cofre do SO, nunca em texto puro.
    lic.chave_ativacao = cofre.proteger(chave)
    lic.maquina_fingerprint = fingerprint
    lic.sistema = settings.redgest_sistema
    lic.status = STATUS_ATIVA
    lic.expira_em = expira
    lic.tolerancia_expira_em = (
        _janela_tolerancia(expira) if expira is not None else None
    )
    limite = dados.get("limite_ativacoes")
    lic.limite_ativacoes = int(limite) if limite is not None else None
    realizadas = dados.get("ativacoes_realizadas")
    lic.ativacoes_realizadas = int(realizadas) if realizadas is not None else None
    lic.entitlements = {
        "primeira_ativacao": bool(dados.get("primeira_ativacao")),
        "limite_ativacoes": lic.limite_ativacoes,
        "ativacoes_realizadas": lic.ativacoes_realizadas,
    }
    lic.ultima_validacao = _agora()
    lic.ultima_tentativa_em = _agora()
    lic.ultimo_erro = None
    db.commit()
    db.refresh(lic)
    _recalcular_estado(lic)


def _marcar_status(db: Session, novo_status: str, motivo: str) -> None:
    """Persiste status + motivo e recompõe o estado (modo de leitura)."""
    lic = _licenca_local(db)
    if lic is None:
        return
    lic.status = novo_status
    lic.ultima_tentativa_em = _agora()
    lic.ultimo_erro = motivo
    db.commit()
    _recalcular_estado(lic)


# ------------------------------------------------- credenciais (Contrato B)
# O par `client_id`/`client_secret` do Contrato B é guardado **num único blob**
# no cofre (`client_id|client_secret`): o RedGest rotaciona o segredo a cada
# `/validar` e os dois valores só fazem sentido juntos. A coluna `client_id`
# (legado) fica nula para não deixar metade do par em texto puro.
_SEPARADOR_CREDENCIAL = "|"


def _montar_credencial(client_id: str, client_secret: str) -> str:
    return f"{(client_id or '').strip()}{_SEPARADOR_CREDENCIAL}{client_secret}"


def _separar_credencial(guardado: str) -> tuple[str, str]:
    if _SEPARADOR_CREDENCIAL not in guardado:
        return guardado.strip(), ""
    client_id, segredo = guardado.split(_SEPARADOR_CREDENCIAL, 1)
    return client_id.strip(), segredo.strip()


def _registrar_falha(db: Session, motivo: str) -> None:
    lic = _licenca_local(db)
    if lic is None:
        return
    lic.ultima_tentativa_em = _agora()
    lic.ultimo_erro = motivo
    db.commit()
    _recalcular_estado(lic)


# ------------------------------------------------------------------- chamada
def _validar_online(db: Session, chave: str) -> dict:
    """Chama o RedGest, atualiza a licença local e devolve a situação."""
    _exigir_credencial()
    fingerprint = _fingerprint()
    corpo = _corpo(chave, fingerprint)
    headers = _cabecalhos(corpo)
    try:
        with _cliente() as cliente:
            resp = cliente.post(CAMINHO_VALIDAR, content=corpo, headers=headers)
    except httpx.HTTPError as exc:
        _registrar_falha(db, f"RedGest inacessível ({type(exc).__name__})")
        raise _indisponivel("validação da chave", exc) from exc

    if resp.status_code == status.HTTP_200_OK:
        dados = _corpo_json(resp)
        if dados.get("valido") is False:
            # A doc de integração §8.2 prevê a recusa dentro de um 200; o
            # servidor real devolve 403/409, mas tratamos os dois formatos.
            _tratar_recusa(db, dados)
        _persistir_ok(db, chave=chave, fingerprint=fingerprint, dados=dados)
        return situacao(db)

    _tratar_erro(db, resp)


def _tratar_recusa(db: Session, dados: dict) -> None:
    """Traduz um `200 {valido: false}` do RedGest (doc §8.2) em erro local."""
    motivo = str(dados.get("motivo") or dados.get("codigo") or "").strip().upper()
    if motivo in _ERROS_DE_LICENCA:
        novo_status, mensagem = _ERROS_DE_LICENCA[motivo]
        _marcar_status(db, novo_status, mensagem)
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=mensagem)
    if motivo == "LIMITE_ATIVACOES_EXCEDIDO":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=_MSG_LIMITE
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=_MSG_CHAVE_DESCONHECIDA
    )


def _tratar_erro(db: Session, resp: httpx.Response) -> None:
    codigo, detalhe = _erro_do_corpo(resp)
    if resp.status_code == status.HTTP_401_UNAUTHORIZED:
        # Assinatura HMAC recusada: bug de integração (credencial/timestamp), não
        # é problema do usuário e não deve entrar em laço de tentativas.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"O servidor de licenças recusou a assinatura da requisição. {detalhe}",
        )
    if resp.status_code == status.HTTP_403_FORBIDDEN and codigo in _ERROS_DE_LICENCA:
        novo_status, motivo = _ERROS_DE_LICENCA[codigo]
        _marcar_status(db, novo_status, motivo)
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=motivo)
    if resp.status_code == status.HTTP_403_FORBIDDEN and codigo in (
        "CHAVE_NAO_ENCONTRADA",
        "CHAVE_INVALIDA",
        "SISTEMA_SEM_CREDENCIAL",
    ):
        # O RedGest resolve o segredo *pela* chave enviada; quando a chave não
        # existe, a resposta é `SISTEMA_SEM_CREDENCIAL` (não há sistema para
        # assinar). Para o usuário isso é "chave não reconhecida"; a segunda
        # frase cobre o caso raro de produto sem `api_key` configurada.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=_MSG_CHAVE_DESCONHECIDA
        )
    if resp.status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"O servidor de licenças recusou a validação: {detalhe}",
        )
    if resp.status_code == status.HTTP_409_CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_MSG_LIMITE,
        )
    if resp.status_code == status.HTTP_400_BAD_REQUEST:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detalhe)
    if resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        # Doc de integração §8.3/§9.2: 429 é transitório — respeita o backoff e
        # nunca revoga a licença.
        _registrar_falha(db, "RedGest limitou a taxa de requisições (429)")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "O servidor de licenças está limitando as requisições. "
                "Tente novamente em instantes."
            ),
        )
    if resp.status_code >= 500:
        _registrar_falha(db, f"RedGest indisponível ({resp.status_code})")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O servidor de licenças está indisponível. Tente novamente em instantes.",
        )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Resposta inesperada do servidor de licenças ({resp.status_code}).",
    )


# ---------------------------------------------------------------- operações
def ativar(
    db: Session,
    *,
    chave_ativacao: str = "",
    cnpj: str = "",
    codigo_licenca: str = "",
) -> dict:
    if _desabilitada():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licenciamento desabilitado nesta build de desenvolvimento.",
        )
    if contrato_b():
        # Import tardio: `licensa_contrato_b` reusa os helpers deste módulo e o
        # import no topo criaria ciclo.
        from app.services import licensa_contrato_b

        return licensa_contrato_b.ativar(db, cnpj=cnpj, codigo_licenca=codigo_licenca)
    chave = _parse_chave(chave_ativacao)
    if not chave:
        # Formato avaliado localmente (doc §4.2): não gasta uma requisição (nem
        # uma tentativa da cota) para descobrir que a chave está truncada.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Chave de ativação inválida. Informe os 16 caracteres de "
                "XXXX-XXXX-XXXX-XXXX (pode digitar/colar com ou sem hífens)."
            ),
        )
    return _validar_online(db, chave)


def renovar(db: Session) -> dict:
    if _desabilitada():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licenciamento desabilitado nesta build de desenvolvimento.",
        )
    lic = _licenca_local(db)
    if lic is None or not lic.chave_ativacao:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Licença ainda não ativada.",
        )
    if contrato_b():
        from app.services import licensa_contrato_b

        return licensa_contrato_b.revalidar(db)
    chave = _chave_em_claro(lic)
    if not chave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Não foi possível ler a chave de ativação guardada no cofre desta "
                "máquina (banco restaurado de outro computador?). Reative a licença."
            ),
        )
    return _validar_online(db, chave)


# ---------------------------------------------------------------------- loop
def _atraso_proximo_ciclo(falhas: int) -> int:
    """Espera até o próximo ciclo: normal sem falhas; backoff crescente com falhas.

    Backoff (1/5/15/60 min por padrão) evita bater no RedGest a cada ciclo quando
    ele está fora, mas volta ao intervalo normal assim que a validação dá certo.
    A doc §9.2 pede jitter: `licenca_backoff_jitter_percentual` (±20% por padrão)
    espalha as instalações que caíram juntas, evitando reconexão em manada.
    """
    if falhas <= 0:
        return settings.licenca_refresh_intervalo_segundos
    backoff = settings.licenca_backoff
    indice = min(falhas - 1, len(backoff) - 1)
    base = backoff[indice]
    jitter = settings.licenca_backoff_jitter_percentual
    if jitter <= 0:
        return base
    fator = random.uniform(1 - jitter / 100, 1 + jitter / 100)
    return max(1, round(base * fator))


def _precisa_revalidar(lic: Licenca) -> bool:
    if lic.ultima_validacao is None:
        return True
    agora = _agora()
    intervalo = settings.licenca_revalidar_a_cada_segundos
    if _estado(lic) == ESTADO_TOLERANCIA:
        # Já vencida: tenta mais cedo para recuperar (ou confirmar) o estado.
        intervalo = settings.licenca_backoff[-1]
    return (agora - lic.ultima_validacao).total_seconds() >= intervalo


def _tentativa_renovacao() -> bool:
    """Uma passada do loop. Devolve `True` quando houve falha de revalidação.

    Falha de rede vira `HTTPException(503)` dentro de `_validar_online`, então
    cai no mesmo `except HTTPException` — sem marcar revogação.
    """
    db = SessionLocal()
    try:
        lic = _licenca_local(db)
        if not _chave_em_claro(lic):
            _recalcular_estado(lic)
            return False
        _recalcular_estado(lic)
        if not _precisa_revalidar(lic):
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
    import asyncio

    falhas = 0
    while True:
        if not _desabilitada():
            try:
                falhou = await asyncio.to_thread(_tentativa_renovacao)
            except Exception:  # noqa: BLE001 — falha externa não derruba o loop
                logger.exception("Falha inesperada na revalidação automática da licença.")
                falhou = True
            falhas = falhas + 1 if falhou else 0
        await asyncio.sleep(_atraso_proximo_ciclo(falhas))
