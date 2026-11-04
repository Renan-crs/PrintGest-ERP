"""Serviços de autenticação: login com bloqueio por tentativas, sessão, troca de senha e logout."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    gerar_token_sessao,
    hash_password,
    hash_token,
    verify_password,
)
from app.deps import verificar_bloqueio
from app.models.core import Usuario, UsuarioSessao

# Hash "neutro" usado para normalizar o tempo de resposta quando o login não
# existe (evita timing oracle de enumeração de usuários — P16 §3.5).
_HASH_NEUTRO = hash_password("--neutralizacao-dummy--")


# 407 não tem constante própria no Starlette; o nome "proxy auth" é o padrão HTTP.
_STATUS_PRIMEIRO_ACESSO = status.HTTP_407_PROXY_AUTHENTICATION_REQUIRED


def login(db: Session, login_input: str, senha: str) -> tuple[str, datetime, Usuario]:
    agora = datetime.now(timezone.utc)
    usuario = db.query(Usuario).filter(Usuario.login == login_input).first()
    if not usuario:
        verify_password(senha, _HASH_NEUTRO)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
        )
    verificar_bloqueio(usuario, agora)

    # M3 (§3.10): primeiro acesso - usuário sem senha definida precisa completar
    if usuario.senha_hash is None or usuario.primeiro_acesso:
        raise HTTPException(
            status_code=_STATUS_PRIMEIRO_ACESSO,
            detail="Primeiro acesso: cadastre sua senha.",
        )

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


def primeiro_acesso(db: Session, login: str, nova_senha: str, usuario_id: int | None = None) -> tuple[str, datetime, Usuario]:
    """Completa o primeiro acesso: define senha e devolve token de sessão."""
    agora = datetime.now(timezone.utc)
    if usuario_id:
        usuario = db.get(Usuario, usuario_id)
    else:
        usuario = db.query(Usuario).filter(Usuario.login == login).first()
    # A mesma mensagem para "não existe" e "já tem senha" evita confirmar quais
    # logins existem (enumeração) — o endpoint é público, como o /login.
    if not usuario or not usuario.primeiro_acesso:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login não encontrado ou já possui senha definida.",
        )
    usuario.senha_hash = hash_password(nova_senha)
    usuario.primeiro_acesso = False
    usuario.falhas_login = 0
    usuario.bloqueado_em = None

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


def trocar_senha(
    db: Session,
    usuario: Usuario,
    senha_atual: str,
    nova_senha: str,
    token_atual: str | None = None,
) -> None:
    """Troca a senha e invalida as demais sessões ativas (P16 §5).

    A sessão que executou a troca (identificada por `token_atual`) permanece
    válida; todas as outras sessões do usuário são encerradas.
    """
    # M3 (§3.10): usuário com primeiro acesso não pode trocar senha normalmente
    if usuario.senha_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário precisa completar primeiro acesso.",
        )
    if not verify_password(senha_atual, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta.",
        )
    usuario.senha_hash = hash_password(nova_senha)
    hash_da_sessao_atual = hash_token(token_atual) if token_atual else None
    ativas = (
        db.query(UsuarioSessao)
        .filter(
            UsuarioSessao.usuario_id == usuario.id,
            UsuarioSessao.encerrada.is_(False),
        )
        .all()
    )
    for sessao in ativas:
        if sessao.token_hash != hash_da_sessao_atual:
            sessao.encerrada = True
    db.commit()


def logout(db: Session, token: str) -> None:
    sessao = (
        db.query(UsuarioSessao)
        .filter(UsuarioSessao.token_hash == hash_token(token))
        .first()
    )
    if sessao:
        sessao.encerrada = True
        db.commit()


def revogar_sessoes(db: Session, usuario_id: int) -> None:
    """Encerra todas as sessões ativas de um usuário (P13/P16).

    Usado no reset de senha por admin: quem redefine a credencial invalida os
    acessos abertos do alvo, forçando novo login com a senha nova.
    """
    sessoes = (
        db.query(UsuarioSessao)
        .filter(
            UsuarioSessao.usuario_id == usuario_id,
            UsuarioSessao.encerrada.is_(False),
        )
        .all()
    )
    for sessao in sessoes:
        sessao.encerrada = True
    db.commit()