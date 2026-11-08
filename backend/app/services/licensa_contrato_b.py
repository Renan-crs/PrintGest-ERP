"""Adaptador do **Contrato B** do RedGest (`Licenca` v4.0, `/api/v1/licencas/`).

Escolhido por `PRINTGEST_REDGEST_CONTRATO=b` (default `c`, o Contrato C vigente).
O desenho segue `docs/migracao_redgest_v4.md` e o manual de integração §7:

- **Ativação** (`POST /api/v1/licencas/{uuid}/ativar/`): handshake com `cnpj` +
  `codigo_licenca`, `Idempotency-Key` obrigatório. O RedGest devolve
  `client_id`/`client_secret` **uma única vez** (§7.2) — os dois vão para o
  cofre do SO (DPAPI), nunca em texto puro, e `client_secret` também é rotacionado
  a cada `/validar` (§7.3).
- **Revalidação** (`POST /api/v1/licencas/{uuid}/validar/`): credenciais +
  `hardware_profile` canônico (o RedGest compara o SHA-256 do JSON ordenado).
  A resposta traz `valida`, `motivo`, `dias_restantes` e `grace_deadline`; é do
  `grace_deadline` que sai a tolerância local (não há `expira_em` no contrato).

Mapeamento de recusa (§7.3/§12) para o estado local:

| `motivo` | Estado local |
|---|---|
| *(vazio, `valida=true`)* | `ativa` |
| `licenca_expirada` | `tolerancia` até o `grace_deadline`, depois `leitura` |
| `licenca_suspensa` | `bloqueada` (leitura imediata; admite regularização) |
| `licenca_bloqueada` | `bloqueada` |
| `licenca_revogada` | `revogada` (terminal) |
| `hardware_divergente` / `sem_hardware_vinculado` / `hardware_nao_enviado` | `bloqueada` com "rebind necessário" |
| `jwt_nao_configurado` | `bloqueada` (bug de infra do RedGest; escalar) |

Falha de transporte **nunca** revoga: vira `503` e o estado anterior é mantido
(mesma política do Contrato C, `docs/plano_resiliencia_licenca.md`).

Pendências conhecidas do adaptador (fase M2 do plano):

- o `token` JWT e o `token_expira_em` são lidos e **não** persistidos — a
  verificação local do JWT (pie-gata do §11.4, que reabilita a operação offline
  sem rede) é o próximo item;
- a origem do `client_secret` depende da estratégia que o RedGest provisionar
  (ver `docs/migracao_redgest_v4.md` §2.2): com `hardware_bound` o vínculo do
  perfil é administrativo e o handshake do §7.2 não se aplica.
"""

import datetime as dt
import json
import re
import unicodedata
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import cofre, cofre_maquina
from app.core.config import settings
from app.models.licenca import Licenca
from app.services import licensa_service as svc

# Motivo -> (status local, mensagem). O prefixo `[RedGest]` marca os motivos
# específicos do contrato para a UI; `licenca_expirada` fica de fora porque o
# estado é derivado da tolerância, não uma recusa imediata.
_MOTIVOS = {
    "licenca_revogada": (
        svc.STATUS_REVOGADA,
        "Licença revogada pelo RedGest. Emita uma licença nova para reativar.",
    ),
    "licenca_suspensa": (
        svc.STATUS_BLOQUEADA,
        "[RedGest] Licença suspensa por inadimplência — regularize o contrato.",
    ),
    "licenca_bloqueada": (
        svc.STATUS_BLOQUEADA,
        "[RedGest] Licença bloqueada pelo RedGest — regularize o contrato.",
    ),
    "hardware_divergente": (
        svc.STATUS_BLOQUEADA,
        (
            "[RedGest] Hardware divergente: esta máquina precisa ser vinculada "
            "novamente à licença (rebind)."
        ),
    ),
    "sem_hardware_vinculado": (
        svc.STATUS_BLOQUEADA,
        (
            "[RedGest] A licença ainda não tem máquina vinculada — solicite o "
            "vínculo ao fornecedor."
        ),
    ),
    "hardware_nao_enviado": (
        svc.STATUS_BLOQUEADA,
        "[RedGest] O servidor de licenças exige o perfil de hardware nesta validação.",
    ),
    "jwt_nao_configurado": (
        svc.STATUS_BLOQUEADA,
        "[RedGest] O servidor de licenças está sem as chaves JWT configuradas.",
    ),
}

_RE_CNPJ = re.compile(r"^\d{14}$")


def _normalizar_cnpj(cnpj: str) -> str:
    """Doc §7.2: CNPJ comparado só por alfanuméricos. `""` quando não tem 14."""
    digitos = re.sub(r"[^0-9A-Za-z]", "", (cnpj or "")).upper()
    return digitos if _RE_CNPJ.match(digitos) else ""


def _normalizar_codigo(codigo: str) -> str:
    return (codigo or "").strip()


def _perfil_hardware() -> dict[str, str]:
    """Perfil canônico enviado no `/validar` (§7.3/§11.4).

    Reusa os identificadores estáveis do Contrato C (`_consultar_hardware`:
    BIOS UUID, serial da placa-mãe, CPU ID e do disco) e traduz `cpu_id`/
    `placa_mae_serial` para as chaves do exemplo do manual (`cpu`/`placa_mae`).
    Os mesmos campos são enviados **sempre com as mesmas chaves e tipos** — um
    valor que muda de tipo gera `hardware_divergente` (o RedGest hasheia o JSON
    canônico). Fallback estável (arquitetura/processador) quando o hardware não
    é legível; nunca hostname/MAC.
    """
    hardware = svc._consultar_hardware()
    if not hardware:
        hardware = {
            "arquitetura": svc.platform.machine(),
            "processador": svc.platform.processor(),
        }
    traduzidas = {"cpu_id": "cpu", "placa_mae_serial": "placa_mae"}
    return {
        traduzidas.get(chave, chave): str(valor)
        for chave, valor in hardware.items()
        if valor
    }


def _entitlements(dados: dict) -> dict:
    valor = dados.get("entitlements")
    return dict(valor) if isinstance(valor, dict) else {}


def _chave_publica_resposta(dados: dict) -> str:
    return str(
        dados.get("chave_publica_pem") or dados.get("jwt_public_key") or ""
    ).strip()


def _tolerancia_de(grace: dt.datetime | None, agora: dt.datetime) -> dt.datetime | None:
    """Tolerância local = `grace_deadline` (§7.3), independente da vigência.

    Com `grace_deadline` ausente (licença vitalícia, por exemplo), deriva uma
    janela de `licenca_tolerancia_horas` a partir de agora — assim uma queda de
    rede logo após a ativação não joga a instalação direto no modo leitura.
    """
    if grace is not None:
        return grace
    return agora + dt.timedelta(hours=settings.licenca_tolerancia_horas)


def _vigencia(grace: dt.datetime | None) -> dt.datetime | None:
    """Vigência (`expira_em`) derivada do `grace_deadline`.

    O `/validar` não devolve `expira_em` de forma confiável: devolve
    `dias_restantes` (arredondado) e `grace_deadline` (absoluto). Como
    `grace_deadline = data_fim + tolerância`, a vigência reconstruída é
    `grace_deadline - licenca_tolerancia_horas` — sem depender do arredondamento.
    """
    if grace is None:
        return None
    return grace - dt.timedelta(hours=settings.licenca_tolerancia_horas)


def _culminancia(dados: dict) -> str:
    return str(dados.get("motivo") or "").strip().lower()


def _vigencia(
    dados: dict, grace: dt.datetime | None, agora: dt.datetime, *, vencida: bool
) -> dt.datetime | None:
    """Vigência (`expira_em`) a partir da resposta do RedGest (§7.2/§7.3/§12).

    O RedGest **não** devolve `expira_em` no Contrato B; as pistas são:

    1. `data_fim` — data explícita de vigência (ativação/renovação);
    2. `dias_restantes` — inteiro, arredondado para baixo; **negativo** quando a
       vigência já venceu;
    3. `grace_deadline = data_fim + tolerância` — absoluto, mas só permite
       reconstruir a vigência (`grace - licenca_tolerancia_horas`) quando as duas
       primeiras não vieram.

    Quando a validação volta com `valida=false` (vigência vencida), a vigência é
    forçada para o passado: o estado passa a ser decidido pela tolerância
    (`grace_deadline`) e depois pelo modo de leitura — nunca por uma data futura
    que o servidor tenha mandado por engano.
    """
    data_fim = svc._parse_dt(dados.get("data_fim"))
    if data_fim is None:
        dias = dados.get("dias_restantes")
        if isinstance(dias, int):
            data_fim = agora + dt.timedelta(days=dias)
    if data_fim is None and grace is not None:
        data_fim = grace - dt.timedelta(hours=settings.licenca_tolerancia_horas)
    if data_fim is not None and vencida and data_fim > agora:
        data_fim = agora
    return data_fim


def _persistir(db: Session, dados: dict, *, codigo: str, cnpj: str) -> Licenca:
    """Faz a linha local refletir uma resposta `valida=true` (ativação/revalidação)."""
    lic = svc._licenca_local(db)
    if lic is None:
        lic = Licenca()
        db.add(lic)
    agora = svc._agora()
    grace = svc._parse_dt(dados.get("grace_deadline"))
    lic.sistema = settings.redgest_sistema
    lic.status = svc.STATUS_ATIVA
    lic.plano = dados.get("plano") or lic.plano
    lic.expira_em = _vigencia(dados, grace, agora, vencida=False)
    lic.tolerancia_expira_em = _tolerancia_de(grace, agora)
    lic.maquina_fingerprint = svc._fingerprint()
    _atualizar_credenciais(lic, dados)
    entitlements = dict(lic.entitlements or {})
    entitlements.pop("motivo_codigo", None)
    # M0 (PRD v3.0 §2): o payload é autoritativo quanto aos módulos — sem a
    # lista, o valor antigo sai (a chave é recopiada ao topo para o gating).
    modulos = svc._modulos_do_payload(dados)
    entitlements.pop("modulos", None)
    if modulos is not None:
        entitlements["modulos"] = modulos
    entitlements["contrato"] = "b"
    entitlements["cnpj"] = cnpj
    licenca_id = str(dados.get("licenca_id") or dados.get("id") or "").strip()
    if licenca_id:
        entitlements["licenca_id"] = licenca_id
    if dados.get("client_id"):
        entitlements["client_id"] = dados["client_id"]
    if dados.get("entitlements"):
        entitlements["redgest"] = _entitlements(dados)
    chave_publica = _chave_publica_resposta(dados)
    if chave_publica:
        entitlements["chave_publica_pem"] = chave_publica
    lic.entitlements = entitlements
    lic.ultima_validacao = agora
    lic.ultima_tentativa_em = agora
    lic.ultimo_erro = None
    # Cópia de recuperação fora do banco: sobrevive à reinstalação e permite
    # reconstruir a linha local com `/validar/` em vez de um novo handshake.
    _registrar_no_cofre_local(dados, codigo=codigo, cnpj=cnpj)
    db.commit()
    db.refresh(lic)
    svc._recalcular_estado(lic)
    return lic


def _atualizar_credenciais(lic: Licenca, dados: dict) -> None:
    """Guarda/rotaciona as credenciais M2M no cofre do SO (§9.4/§11.4).

    O `client_secret` é rotacionado pelo `/validar`; sempre que a resposta trouxer
    um valor novo, ele substitui o antigo. `client_id` fica embutido no blob para
    o par ser lido junto.
    """
    client_id = (dados.get("client_id") or "").strip()
    segredo = (dados.get("client_secret") or "").strip()
    if not segredo:
        return
    lic.client_secret = cofre.proteger(svc._montar_credencial(client_id, segredo))
    lic.client_id = None


def _credenciais_do_cofre(lic: Licenca) -> tuple[str, str]:
    guardado = cofre.revelar(lic.client_secret or "")
    if not guardado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Não foi possível ler as credenciais da licença no cofre desta "
                "máquina (banco restaurado de outro computador?). Reative a licença."
            ),
        )
    return svc._separar_credencial(guardado)


# ------------------------------------- recuperação fora do banco (reinstalação)
def _sem_acento(texto: str) -> str:
    """Minúsculas sem acentos — comparação tolerante das mensagens do RedGest."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    return decomposto.encode("ascii", "ignore").decode("ascii").lower()


def _material_completo(material: dict) -> bool:
    return bool(
        material.get("client_id")
        and material.get("client_secret")
        and material.get("codigo")
    )


def _material_combina(material: dict, numero: str, codigo: str) -> bool:
    """O material guardado é da licença (CNPJ + código) que o usuário digitou?"""
    return (
        _material_completo(material)
        and str(material.get("cnpj") or "") == numero
        and str(material.get("codigo") or "").casefold() == codigo.casefold()
    )


def _linha_combina(lic: Licenca | None, numero: str, codigo: str) -> bool:
    """A linha local já corresponde à licença digitada (mesmo CNPJ + código)?"""
    if lic is None:
        return False
    entitlements = dict(lic.entitlements or {})
    guardado = svc._chave_em_claro(lic)
    return (
        str(entitlements.get("cnpj") or "") == numero
        and bool(guardado)
        and guardado.casefold() == codigo.casefold()
    )


def _registrar_no_cofre_local(dados: dict, *, codigo: str, cnpj: str) -> None:
    """Mantém a cópia de recuperação da ativação na máquina.

    Chamado em toda resposta bem-sucedida (ativação **e** revalidação): o
    `/validar` rotaciona o `client_secret`, então o arquivo precisa acompanhar.
    Quando a resposta não traz o par (servidor que não o ecoa), preserva o que
    já estava guardado.
    """
    atual = cofre_maquina.ler()
    client_id = str(dados.get("client_id") or "").strip()
    segredo = str(dados.get("client_secret") or "").strip()
    if not (client_id and segredo):
        client_id = client_id or str(atual.get("client_id") or "")
        segredo = segredo or str(atual.get("client_secret") or "")
    if not (client_id and segredo):
        return
    codigo_final = codigo or str(atual.get("codigo") or "")
    if not codigo_final:
        return
    licenca_id = str(
        dados.get("licenca_id")
        or dados.get("id")
        or atual.get("licenca_id")
        or codigo_final
    ).strip()
    cofre_maquina.guardar(
        {
            "versao": 1,
            "cnpj": cnpj or str(atual.get("cnpj") or ""),
            "codigo": codigo_final,
            "licenca_id": licenca_id,
            "client_id": client_id,
            "client_secret": segredo,
            "atualizado_em": svc._agora().isoformat(),
        }
    )


def _credencial_recusada(exc: HTTPException) -> bool:
    """400 específico de credencial recusada pelo `/validar` (HTTP 403 do RedGest)."""
    return exc.status_code == status.HTTP_400_BAD_REQUEST and "credenciais" in (
        _sem_acento(str(exc.detail or ""))
    )


def _erro_ativacao_ja_existente(exc: HTTPException) -> bool:
    """O `/ativar/` recusou porque a licença já tem credenciais M2M emitidas."""
    if exc.status_code not in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_409_CONFLICT,
    ):
        return False
    texto = _sem_acento(str(exc.detail or ""))
    return any(
        marca in texto
        for marca in (
            "ja possui ativacao",
            "ativacao ativa",
            "reset das credenciais",
            "credenciais m2m",
            "credenciais ja emitidas",
        )
    )


def _erro_credenciais_perdidas(exc: HTTPException, codigo: str) -> HTTPException:
    """Mensagem acionável quando não há cópia local para recuperar a licença."""
    return HTTPException(
        status_code=exc.status_code,
        detail=(
            "Esta licença já foi ativada e não foi possível recuperar as "
            f"credenciais desta instalação. Guarde o código {codigo} e peça ao "
            "suporte do RedGest o reset das credenciais M2M; depois ative "
            "novamente — nas próximas reinstalações a recuperação será automática."
        ),
    )


def _material_da_linha(lic: Licenca | None, *, codigo: str, cnpj: str) -> dict | None:
    """Material de ativação legível na própria linha local (``None`` se não há)."""
    if lic is None:
        return None
    try:
        client_id, segredo = _credenciais_do_cofre(lic)
    except HTTPException:
        return None
    if not client_id or not segredo:
        return None
    entitlements = dict(lic.entitlements or {})
    return {
        "client_id": client_id,
        "client_secret": segredo,
        "licenca_id": str(entitlements.get("licenca_id") or codigo or "").strip(),
        "cnpj": cnpj,
        "codigo": codigo,
    }


def _validar_com_material(
    db: Session, material: dict, *, cnpj: str, codigo: str
) -> dict:
    """Chama `/validar/` com um material já resolvido e persiste o resultado.

    É o caminho comum da revalidação periódica e da recuperação após
    reinstalação (linha local perdida ou blob DPAPI do banco ilegível). Não gasta
    o handshake de uso único do §7.2.
    """
    licenca_id = str(material.get("licenca_id") or codigo or "").strip()
    corpo = {
        "client_id": str(material.get("client_id") or "").strip(),
        "client_secret": str(material.get("client_secret") or "").strip(),
        "hardware_profile": _perfil_hardware(),
    }
    dados = _requisitar(
        db,
        svc._cliente_com_idempotencia(uuid.uuid4().hex),
        f"/api/v1/licencas/{licenca_id}/validar/",
        corpo,
        contexto="validação da licença",
    )
    if dados.get("valida") is False:
        motivo = _culminancia(dados)
        if motivo == "licenca_expirada" and svc._licenca_local(db) is None:
            # Reinstalação dentro do grace: reconstrói a linha em tolerância em
            # vez de bloquear (o `/validar` não devolve `data_fim` confiável).
            grace = svc._parse_dt(dados.get("grace_deadline"))
            if grace is not None and grace > svc._agora():
                lic = _persistir(db, dados, codigo=codigo, cnpj=cnpj)
                lic.chave_ativacao = cofre.proteger(codigo)
                db.commit()
                svc._recalcular_estado(lic)
                return svc.situacao(db)
        _tratar_valida_false(db, dados, origem="recuperacao")
        return svc.situacao(db)
    lic = _persistir(db, dados, codigo=codigo, cnpj=cnpj)
    # A coluna da chave guarda o `codigo_licenca` cifrado: mantém `_estado()`
    # (que exige uma chave legível) e o mascaramento da situação funcionando.
    lic.chave_ativacao = cofre.proteger(codigo)
    db.commit()
    svc._recalcular_estado(lic)
    return svc.situacao(db)


def _erro_transporte(db: Session, contexto: str, exc: Exception) -> HTTPException:
    svc._registrar_falha(db, f"RedGest inacessível ({type(exc).__name__})")
    return svc._indisponivel(contexto, exc)


def _erro_de_resposta(db: Session, resp: httpx.Response) -> HTTPException:
    """Traduz códigos HTTP do Contrato B (§10.3) sem nunca revogar por engano."""
    _codigo, detalhe = svc._erro_do_corpo(resp)
    if resp.status_code == status.HTTP_401_UNAUTHORIZED:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"O servidor de licenças recusou as credenciais enviadas. {detalhe}",
        )
    if resp.status_code == status.HTTP_403_FORBIDDEN:
        # §10.3: credencial inválida -> reconquistar a ativação (não é rede).
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "O servidor de licenças recusou as credenciais desta instalação. "
                "Reative a licença com o CNPJ e o código; se o erro persistir, "
                "peça ao suporte o reset das credenciais M2M."
            ),
        )
    if resp.status_code == status.HTTP_404_NOT_FOUND:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Licença não encontrada no servidor de licenças (código conferido?)."
            ),
        )
    if resp.status_code == status.HTTP_409_CONFLICT:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalhe)
    if resp.status_code == status.HTTP_400_BAD_REQUEST:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detalhe)
    if resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        svc._registrar_falha(db, "RedGest limitou a taxa de requisições (429)")
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "O servidor de licenças está limitando as requisições. "
                "Tente novamente em instantes."
            ),
        )
    if resp.status_code >= 500:
        svc._registrar_falha(db, f"RedGest indisponível ({resp.status_code})")
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "O servidor de licenças está indisponível. Tente novamente em "
                "instantes."
            ),
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Resposta inesperada do servidor de licenças ({resp.status_code}).",
    )


def _tratar_valida_false(db: Session, dados: dict, *, origem: str) -> None:
    """Aplica uma recusa `valida=false` do `/validar` (§7.3) e levanta o 423/erro."""
    motivo = _culminancia(dados)
    if motivo in _MOTIVOS:
        status_licenca, mensagem = _MOTIVOS[motivo]
        svc._bloquear(db, status_licenca, mensagem, codigo=motivo)
    if motivo == "licenca_expirada":
        # Dentro do grace a instalação segue operando; passado o grace, leitura.
        lic = svc._licenca_local(db)
        grace = svc._parse_dt(dados.get("grace_deadline"))
        agora = svc._agora()
        if lic is not None and grace is not None:
            lic.status = svc.STATUS_ATIVA
            lic.tolerancia_expira_em = grace
            svc._registrar_falha(db, "Vigência vencida no RedGest (tolerância).")
            lic.expira_em = agora - dt.timedelta(seconds=1)
            db.commit()
            svc._recalcular_estado(lic)
            if svc._estado(lic) == svc.ESTADO_LEITURA:
                svc._bloquear(
                    db,
                    svc.STATUS_EXPIRADA,
                    "Licença expirada. Renove o contrato para reativar.",
                    codigo=motivo,
                )
            # Não bloqueamos → retornamos situação normal
            return
        svc._bloquear(
            db,
            svc.STATUS_EXPIRADA,
            "Licença expirada. Renove o contrato para reativar.",
            codigo=motivo,
        )
    mensagem = (
        "O servidor de licenças recusou a validação da licença"
        f"{f' ({motivo})' if motivo else ''}. Acione o suporte."
    )
    svc._bloquear(db, svc.STATUS_BLOQUEADA, mensagem, codigo=motivo or origem)


def _requisitar(
    db: Session,
    cliente: httpx.Client,
    caminho: str,
    corpo: dict,
    *,
    contexto: str,
) -> dict:
    corpo_bytes = json.dumps(corpo, separators=(",", ":")).encode("utf-8")
    try:
        with cliente:
            resp = cliente.post(
                caminho,
                content=corpo_bytes,
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise _erro_transporte(db, contexto, exc) from exc
    svc._correlacionar(resp)
    if resp.status_code != status.HTTP_200_OK:
        raise _erro_de_resposta(db, resp)
    return svc._corpo_json(resp)


# --------------------------------------------------------------- operações
def ativar(db: Session, *, cnpj: str, codigo_licenca: str) -> dict:
    """Ativa a licença — ou recupera a ativação já existente nesta máquina.

    Ordem (a mesma máquina dentro da vigência reutiliza a licença sem suporte):

    1. linha local legível e correspondente ao CNPJ + código -> `/validar/`;
    2. cópia de recuperação da máquina (sobrevive à reinstalação) -> `/validar/`;
    3. handshake `/ativar/` (primeira ativação).

    Se o RedGest recusar o handshake porque a licença já possui credenciais M2M
    (§7.2, segredo emitido uma única vez) e não houver cópia local, a mensagem
    orienta o reset de suporte.
    """
    if not settings.redgest_url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Integração com o servidor de licenças sem URL configurada.",
        )
    numero = _normalizar_cnpj(cnpj)
    if not numero:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CNPJ inválido. Informe os 14 dígitos do titular da licença.",
        )
    codigo = _normalizar_codigo(codigo_licenca)
    if not codigo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe o código da licença entregue na contratação.",
        )

    # 1) A instalação já tem o par no cofre do banco para esta mesma licença:
    #    revalida (rotaciona o secret) em vez de tentar um novo handshake.
    lic = svc._licenca_local(db)
    if _linha_combina(lic, numero, codigo):
        material_linha = _material_da_linha(lic, codigo=codigo, cnpj=numero)
        if material_linha is not None:
            try:
                return _validar_com_material(
                    db, material_linha, cnpj=numero, codigo=codigo
                )
            except HTTPException as exc:
                if not _credencial_recusada(exc):
                    raise

    # 2) Linha perdida (reinstalação/recriação do banco): reconstrói pelo cofre
    #    local da máquina, sem consumir um novo handshake.
    material = cofre_maquina.ler()
    if _material_combina(material, numero, codigo):
        try:
            return _validar_com_material(db, material, cnpj=numero, codigo=codigo)
        except HTTPException as exc:
            if not _credencial_recusada(exc):
                raise
            # Par local não vale mais (segredo rotacionado sem resposta): o
            # handshake abaixo devolve a mensagem correta — normalmente "já
            # ativada", que vira a orientação de reset.

    # 3) Primeira ativação nesta instalação.
    corpo = {
        "cnpj": numero,
        "codigo_licenca": codigo,
        "hardware_profile": _perfil_hardware(),
    }
    try:
        dados = _requisitar(
            db,
            svc._cliente_com_idempotencia(uuid.uuid4().hex),
            f"/api/v1/licencas/{codigo}/ativar/",
            corpo,
            contexto="ativação da licença",
        )
    except HTTPException as exc:
        if _erro_ativacao_ja_existente(exc):
            raise _erro_credenciais_perdidas(exc, codigo) from exc
        raise
    lic = _persistir(db, dados, codigo=codigo, cnpj=numero)
    # A coluna da chave guarda o `codigo_licenca` cifrado: mantém `_estado()`
    # (que exige uma chave legível) e o mascaramento da situação funcionando.
    lic.chave_ativacao = cofre.proteger(codigo)
    db.commit()
    svc._recalcular_estado(lic)
    return svc.situacao(db)


def revalidar(db: Session) -> dict:
    """`/validar` do §7.3: credenciais M2M + perfil de hardware.

    Sem a linha local (ou com o par ilegível), tenta a cópia de recuperação da
    máquina antes de pedir reativação — cobre reinstalação e banco restaurado de
    outro computador.
    """
    lic = svc._licenca_local(db)
    if lic is None:
        material = cofre_maquina.ler()
        if _material_completo(material):
            return _validar_com_material(
                db,
                material,
                cnpj=str(material.get("cnpj") or ""),
                codigo=str(material.get("codigo") or ""),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Licença ainda não ativada."
        )

    entitlements = dict(lic.entitlements or {})
    codigo_local = svc._chave_em_claro(lic)
    licenca_id = str(entitlements.get("licenca_id") or codigo_local or "").strip()
    codigo = codigo_local or licenca_id
    cnpj = str(entitlements.get("cnpj") or "")
    material = _material_da_linha(lic, codigo=codigo, cnpj=cnpj)

    if material is None:
        # Banco sem o par legível (linha restaurada de outra máquina): a cópia
        # da máquina é a única saída sem reset. Se o código local é legível,
        # ela precisa ser da mesma licença.
        recuperavel = cofre_maquina.ler()
        if _material_completo(recuperavel) and (
            not codigo_local
            or str(recuperavel.get("codigo") or "").casefold()
            == codigo_local.casefold()
        ):
            return _validar_com_material(
                db,
                recuperavel,
                cnpj=cnpj or str(recuperavel.get("cnpj") or ""),
                codigo=codigo_local or str(recuperavel.get("codigo") or ""),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Credenciais da licença incompletas nesta instalação. "
                "Reative a licença com o CNPJ e o código."
            ),
        )

    return _validar_com_material(db, material, cnpj=cnpj, codigo=codigo)
