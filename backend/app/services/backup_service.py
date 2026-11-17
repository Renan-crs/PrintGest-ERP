"""Backup local e espelho no Neon (PRD v3.3 §3.3/§3.4/§3.7).

REGRAS DE SEGURANÇA:
- pg_dump/pg_restore são chamados com **lista de argumentos** (nunca shell=True).
- O destino é validado como diretório existente; nunca apagamos dados do cliente.
- O envio ao Neon só ocorre com `termo_backup.aceito = true` (RF-LG-01).
- O dump local continua disponível em QUALQUER estado de licença (RF-BK-05).
- Nenhuma credencial é gravada em arquivo de texto: a URL do Neon fica no
  cofre de integrações (`cofre_integracoes`) quando usarmos o espelho.

NOTA: a restauração efetiva em máquina limpa exige a ferramenta `pg_restore`
disponível no servidor. Aqui expomos o comando seguro e registramos o resultado.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.plataforma import BackupConfig, TermoBackup

_TERMO_VERSAO = "1.0"


def _config(db: Session, filial_id: int, criar: bool = True) -> BackupConfig | None:
    cfg = (
        db.query(BackupConfig).filter(BackupConfig.filial_id == filial_id).first()
    )
    if cfg is None and criar:
        cfg = BackupConfig(filial_id=filial_id, horario="02:00", retencao_dias=14)
        db.add(cfg)
        db.flush()
    return cfg


def obter(db: Session, *, filial_id: int) -> dict:
    cfg = _config(db, filial_id)
    if cfg is None:
        return {}
    return {
        "id": cfg.id,
        "filial_id": cfg.filial_id,
        "horario": cfg.horario,
        "retencao_dias": cfg.retencao_dias,
        "destino": cfg.destino,
        "neon_espelho": bool(cfg.neon_espelho),
        "ultimo_backup_em": cfg.ultimo_backup_em,
        "ultimo_backup_ok": cfg.ultimo_backup_ok,
        "ultimo_backup_tamanho": cfg.ultimo_backup_tamanho,
        "ultimo_envio_neon_em": cfg.ultimo_envio_neon_em,
        "ultimo_envio_neon_ok": cfg.ultimo_envio_neon_ok,
    }


def configurar(db: Session, *, filial_id: int, dados: dict) -> dict:
    cfg = _config(db, filial_id)
    horario = dados.get("horario")
    if horario:
        try:
            horas, minutos = horario.split(":")
            if not (0 <= int(horas) <= 23 and 0 <= int(minutos) <= 59):
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(400, "horario deve estar no formato HH:MM.")
    destino = dados.get("destino")
    if destino and not Path(destino).is_dir():
        raise HTTPException(400, "O diretório de destino não existe.")
    for chave in ("horario", "retencao_dias", "destino", "neon_espelho"):
        if chave in dados and dados[chave] is not None:
            setattr(cfg, chave, dados[chave])
    cfg.atualizado_em = datetime.now(UTC)
    db.commit()
    db.refresh(cfg)
    return obter(db, filial_id=filial_id)


def termo(db: Session, *, filial_id: int) -> dict:
    atual = (
        db.query(TermoBackup)
        .filter(TermoBackup.filial_id == filial_id)
        .order_by(TermoBackup.aceito_em.desc(), TermoBackup.id.desc())
        .first()
    )
    if atual is None:
        return {"aceito": False, "versao": _TERMO_VERSAO}
    return {
        "aceito": bool(atual.aceito),
        "versao": atual.versao,
        "aceito_em": atual.aceito_em,
        "usuario_id": atual.usuario_id,
    }


def aceitar_termo(
    db: Session, *, filial_id: int, usuario_id: int, aceito: bool, versao: str,
    ip: str | None = None
) -> dict:
    if aceito is False:
        # RF-LG-02: desativar — auditoria registra a retratação.
        registro = TermoBackup(
            filial_id=filial_id, versao=versao, aceito=False,
            usuario_id=usuario_id, ip=ip,
        )
        db.add(registro)
        db.commit()
        return termo(db, filial_id=filial_id)
    cfg = _config(db, filial_id)
    cfg.neon_espelho = True
    registro = TermoBackup(
        filial_id=filial_id, versao=versao or _TERMO_VERSAO,
        aceito=True, usuario_id=usuario_id, ip=ip,
    )
    db.add(registro)
    db.commit()
    return termo(db, filial_id=filial_id)


def _pg_bin() -> Path:
    candidatos = [
        Path(settings.pg_raiz) / "pgsql" / "bin" if settings.pg_raiz else None,
        Path(__file__).resolve().parents[3] / ".dev" / "postgres" / "pgsql" / "bin",
    ]
    for pasta in candidatos:
        if pasta and (pasta / "pg_dump.exe").exists():
            return pasta
    return candidatos[-1]  # type: ignore[return-value]


def destino_padrao() -> Path:
    raiz = Path(__file__).resolve().parents[3] / ".dev" / "backups"
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def executar_backup(db: Session, *, filial_id: int, usuario_id: int) -> dict:
    """pg_dump -Fc em destino local. Nunca apaga o dump anterior."""
    cfg = _config(db, filial_id)
    destino = Path(cfg.destino) if cfg.destino else destino_padrao()
    destino.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    arquivo = destino / f"printgest_{filial_id}_{carimbo}.dump"
    agora = datetime.now(UTC)

    url = settings.database_url
    # psycopg/SQLAlchemy → URL aceita pelo pg_dump (sem o driver '+psycopg').
    url_cli = url.replace("postgresql+psycopg://", "postgresql://", 1)
    binario = _pg_bin() / "pg_dump.exe"
    try:
        comando = [str(binario), "-Fc", "-f", str(arquivo), url_cli]
        processo = subprocess.run(comando, capture_output=True, text=True, timeout=600)
        ok = processo.returncode == 0 and arquivo.exists()
        tamanho = arquivo.stat().st_size if arquivo.exists() else None
        mensagem = (
            "Backup local concluído." if ok
            else f"pg_dump falhou: {(processo.stderr or 'erro desconhecido')[:300]}"
        )
    except (OSError, subprocess.SubprocessError) as exc:
        ok, tamanho = False, None
        mensagem = f"Falha ao executar pg_dump: {type(exc).__name__}."
    cfg.ultimo_backup_em = agora
    cfg.ultimo_backup_ok = ok
    cfg.ultimo_backup_tamanho = tamanho
    db.commit()
    return {
        "ok": ok,
        "caminho": str(arquivo) if ok else None,
        "tamanho": tamanho,
        "mensagem": mensagem,
        "executado_em": agora,
    }


def script_restauracao(*, arquivo: str, recriar: bool = False) -> list[str]:
    """Comando SEGURO de restore (lista de args, sem shell) para suporte."""
    binario = _pg_bin() / "pg_restore.exe"
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    partes = [str(binario), "--clean", "--if-exists", "-d", url, arquivo]
    return partes


def rotacionar(db: Session, *, filial_id: int) -> int:
    """Remove dumps antigos DESTE tenant, respeitando retenção."""
    cfg = _config(db, filial_id)
    pasta = Path(cfg.destino) if cfg.destino else destino_padrao()
    if not pasta.is_dir():
        return 0
    limite = datetime.now(UTC) - timedelta(days=int(cfg.retencao_dias or 14))
    removidos = 0
    prefixo = f"printgest_{filial_id}_"
    for arquivo in pasta.glob(f"{prefixo}*.dump"):
        criado = datetime.fromtimestamp(arquivo.stat().st_mtime, tz=UTC)
        if criado < limite:
            arquivo.unlink()
            removidos += 1
    return removidos
