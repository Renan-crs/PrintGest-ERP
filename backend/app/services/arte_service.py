"""Arte, prova e aprovação (M3, PRD v3.0 §3.5).

Ciclo: **upload da arte** (v1, v2…) → **envio da prova** (link para o
cliente) → **decisão** (aprovada / ajuste com comentários) → produção
liberada quando aprovada (regra configurável por produto).

Arquivos ficam em `uploads/{os_id}/` no disco local; o caminho e o hash
SHA-256 vão para `arte_versao` (NFR de arquivos: tipo, tamanho e hash;
extensões executáveis bloqueadas).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import DecisaoArte, TipoLinkPublico
from app.models.movimento import (
    ArteAprovacao,
    ArteVersao,
    LinkPublico,
    OrdemServico,
)

# Extensões permitidas (§3.5: "extensões executáveis bloqueadas")
_EXTENSOES_BLOQUEADAS = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".msi", ".dll", ".com", ".scr", ".vbs", ".js"}
_MAX_TAMANHO = 50 * 1024 * 1024  # 50 MB


def _pasta_uploads(os_id: int) -> Path:
    pasta = Path(settings.database_url.split("@")[-1].split("/")[0])  # fallback
    # Usa o diretório do projeto em dev; em produção, virá do settings
    base = Path(__file__).resolve().parents[2] / "uploads" / str(os_id)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _validar_arquivo(nome: str, tamanho: int) -> None:
    ext = Path(nome).suffix.lower()
    if ext in _EXTENSOES_BLOQUEADAS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensão {ext} não é permitida para arte.",
        )
    if tamanho > _MAX_TAMANHO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Arquivo maior que {_MAX_TAMANHO // (1024 * 1024)} MB.",
        )
    if tamanho <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo vazio.",
        )


def enviar_versao(
    db: Session,
    *,
    os_id: int,
    filial_id: int,
    usuario_id: int,
    arquivo: UploadFile,
) -> ArteVersao:
    """Faz upload de uma nova versão da arte (v1, v2… — auto-incremento)."""
    os_obj = db.query(OrdemServico).filter(
        OrdemServico.id == os_id, OrdemServico.filial_id == filial_id
    ).first()
    if not os_obj:
        raise HTTPException(status_code=404, detail="Ordem de serviço não encontrada.")

    conteudo = arquivo.file.read()
    _validar_arquivo(arquivo.filename or "sem-nome", len(conteudo))
    hash_sha256 = hashlib.sha256(conteudo).hexdigest()

    ultima = (
        db.query(ArteVersao)
        .filter(ArteVersao.os_id == os_id)
        .order_by(ArteVersao.versao.desc())
        .first()
    )
    proxima = (ultima.versao + 1) if ultima else 1

    # grava no disco
    pasta = _pasta_uploads(os_id)
    destino = pasta / f"v{proxima}_{arquivo.filename}"
    destino.write_bytes(conteudo)

    versao = ArteVersao(
        filial_id=filial_id,
        os_id=os_id,
        versao=proxima,
        nome_arquivo=arquivo.filename or f"versao_{proxima}",
        caminho=str(destino),
        hash_sha256=hash_sha256,
        tamanho_bytes=len(conteudo),
        criado_por=usuario_id,
    )
    db.add(versao)
    db.commit()
    db.refresh(versao)
    return versao


def listar_versoes(db: Session, *, os_id: int, filial_id: int) -> list[ArteVersao]:
    return (
        db.query(ArteVersao)
        .join(OrdemServico)
        .filter(ArteVersao.os_id == os_id, OrdemServico.filial_id == filial_id)
        .order_by(ArteVersao.versao.desc())
        .all()
    )


def registrar_decisao(
    db: Session,
    *,
    versao_id: int,
    filial_id: int,
    decisao: DecisaoArte,
    comentarios: str | None = None,
    ip: str | None = None,
    usuario_id: int | None = None,
) -> ArteAprovacao:
    """Registra a decisão do cliente sobre uma versão (aprovada / ajuste)."""
    versao = (
        db.query(ArteVersao)
        .filter(ArteVersao.id == versao_id, ArteVersao.filial_id == filial_id)
        .first()
    )
    if not versao:
        raise HTTPException(status_code=404, detail="Versão da arte não encontrada.")

    if decisao == DecisaoArte.AJUSTE and not (comentarios or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Informe o ajuste solicitado pelo cliente.",
        )

    aprovacao = ArteAprovacao(
        filial_id=filial_id,
        versao_id=versao_id,
        decisao=decisao.value,
        comentarios=comentarios,
        ip=ip,
        criado_por=usuario_id,
    )
    db.add(aprovacao)
    db.commit()
    db.refresh(aprovacao)
    return aprovacao


def estado_arte(db: Session, *, os_id: int) -> str:
    """Estado derivado da arte da OS (§3.5).

    Estados: `sem_arte` | `aguardando_aprovacao` | `ajuste_solicitado` |
    `aprovada`. O status da OS incorpora "Aguardando arte" e
    "Aguardando aprovação" a partir daqui.
    """
    versoes = (
        db.query(ArteVersao)
        .filter(ArteVersao.os_id == os_id)
        .order_by(ArteVersao.versao.desc())
        .all()
    )
    if not versoes:
        return "sem_arte"

    ultima = versoes[0]
    decisao = (
        db.query(ArteAprovacao)
        .filter(ArteAprovacao.versao_id == ultima.id)
        .order_by(ArteAprovacao.criado_em.desc())
        .first()
    )
    if decisao is None:
        return "aguardando_aprovacao"
    if decisao.decisao == DecisaoArte.APROVADA.value:
        return "aprovada"
    return "ajuste_solicitado"


def gerar_link(
    db: Session,
    *,
    os_id: int,
    filial_id: int,
    tipo: TipoLinkPublico = TipoLinkPublico.PROVA,
    expira_horas: int = 72,
) -> LinkPublico:
    """Gera um link público com token aleatório e expiração (§3.5).

    O relay hospedado (D-03) resolve o token; aqui ficam o token e a
    expiração. Uso único: quando `usado=True`, o token morre.
    """
    token = secrets.token_urlsafe(32)
    link = LinkPublico(
        filial_id=filial_id,
        os_id=os_id,
        token=token,
        tipo=tipo.value,
        expira_em=datetime.utcnow() + timedelta(hours=expira_horas),
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def para_out_versao(versao: ArteVersao) -> dict:
    """Serializa uma versão para a resposta da API (sem o caminho no disco)."""
    return {
        "id": versao.id,
        "os_id": versao.os_id,
        "versao": versao.versao,
        "nome_arquivo": versao.nome_arquivo,
        "hash_sha256": versao.hash_sha256,
        "tamanho_bytes": versao.tamanho_bytes,
        "criado_em": versao.criado_em,
    }


def para_out_aprovacao(aprovacao: ArteAprovacao) -> dict:
    return {
        "id": aprovacao.id,
        "versao_id": aprovacao.versao_id,
        "decisao": aprovacao.decisao,
        "comentarios": aprovacao.comentarios,
        "ip": aprovacao.ip,
        "criado_em": aprovacao.criado_em,
    }
