"""Dependências FastAPI: sessão de banco, autenticação, RBAC e escopo de filial."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token
from app.db import SessionLocal
from app.models.core import Usuario, UsuarioSessao
from app.models.enums import NivelAcesso

RANK = {NivelAcesso.ADMIN: 4, NivelAcesso.GERENTE: 3, NivelAcesso.OPERADOR: 2, NivelAcesso.CAIXA: 1}


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]


def _autenticar(token: str, db: Session) -> Usuario:
    token_hash = hash_token(token)
    sessao = (
        db.query(UsuarioSessao)
        .filter(
            UsuarioSessao.token_hash == token_hash,
            UsuarioSessao.encerrada.is_(False),
        )
        .first()
    )
    if not sessao:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida. Faça login novamente.",
        )
    agora = datetime.now(timezone.utc)
    if sessao.expira_em < agora:
        sessao.encerrada = True
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada por inatividade. Faça login novamente.",
        )
    usuario = db.get(Usuario, sessao.usuario_id)
    if not usuario or not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário inativo ou inexistente.",
        )
    # Expiração deslizante por inatividade: cada requisição renova o TTL.
    sessao.expira_em = agora + timedelta(minutes=settings.session_ttl_minutes)
    db.commit()
    return usuario


def get_usuario_atual(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Usuario:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária (Bearer token).",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação vazio.",
        )
    return _autenticar(token, db)


UsuarioDep = Annotated[Usuario, Depends(get_usuario_atual)]


def require_nivel(*niveis: NivelAcesso):
    """Permite apenas usuários com nível igual ou superior ao menor nível informado."""

    rank_minimo = min(RANK.get(n, 1) for n in niveis) if niveis else 1

    def _check(usuario: UsuarioDep) -> Usuario:
        if RANK.get(usuario.nivel_acesso, 0) < rank_minimo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado: nível de permissão insuficiente.",
            )
        return usuario

    return _check


def require_perfis(*niveis: NivelAcesso):
    """Permite apenas os perfis listados (RBAC **não hierárquico** — PRD v2.1 §5).

    Diferente de `require_nivel`, não usa o rank: `caixa` vê Financeiro/Fiscal,
    enquanto `operador` (rank maior) não vê. É o que o menu v2.1 expressa.
    """
    permitidos = set(niveis)

    def _check(usuario: UsuarioDep) -> Usuario:
        if usuario.nivel_acesso not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado: nível de permissão insuficiente.",
            )
        return usuario

    return _check


def get_filial_atual(usuario: UsuarioDep) -> int:
    """Filial efetiva do usuário — MVP opera com filial 1 quando não definida."""
    return usuario.filial_id or 1


FilialDep = Annotated[int, Depends(get_filial_atual)]


def verificar_bloqueio(usuario: Usuario, agora: datetime) -> None:
    if usuario.bloqueado_em and usuario.bloqueado_em > agora:
        remaining = usuario.bloqueado_em - agora
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Usuário temporariamente bloqueado por excesso de tentativas. "
                f"Tente novamente em {int(remaining.total_seconds() // 60) + 1} min."
            ),
        )