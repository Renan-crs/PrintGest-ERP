"""Serviços de autenticação: login com bloqueio por tentativas, sessão e logout."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import gerar_token_sessao, hash_token, verify_password
from app.deps import verificar_bloqueio
from app.models.core import Usuario, UsuarioSessao


def login(db: Session, login_input: str, senha: str) -> tuple[str, datetime, Usuario]:
    agora = datetime.now(timezone.utc)
    usuario = db.query(Usuario).filter(Usuario.login == login_input).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
        )
    verificar_bloqueio(usuario, agora)

    if not verify_password(senha, usuario.senha_hash):
        usuario.falhas_login += 1
        if usuario.falhas_login >= settings.login_max_falhas:
            usuario.bloqueado_em = agora + timedelta(minutes=settings.bloqueio_minutos)
            usuario.falhas_login = 0
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
        )

    usuario.falhas_login = 0
    usuario.bloqueado_em = None
    usuario.ultimo_login = agora

    token = gerar_token_sessao()
    expira = agora + timedelta(minutes=settings.session_ttl_minutes)
    sessao = UsuarioSessao(
        usuario_id=usuario.id,
        token_hash=hash_token(token),
        expira_em=expira,
    )
    db.add(sessao)
    db.commit()
    return token, expira, usuario


def sessao_por_token(db: Session, token: str) -> Usuario:
    from app.deps import _autenticar  # evita import circular

    return _autenticar(token, db)


def logout(db: Session, token: str) -> None:
    sessao = (
        db.query(UsuarioSessao)
        .filter(UsuarioSessao.token_hash == hash_token(token))
        .first()
    )
    if sessao:
        sessao.encerrada = True
        db.commit()