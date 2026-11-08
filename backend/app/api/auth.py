from typing import Annotated

from fastapi import APIRouter, Header

from app.deps import DbDep, UsuarioDep
from app.schemas import (
    ItemResponse,
    LoginIn,
    LoginOut,
    PrimeiroAcessoIn,
    TrocarSenhaIn,
    UsuarioSessaoOut,
)
from app.services.auth_service import (
    login,
    logout,
)
from app.services.auth_service import (
    primeiro_acesso as service_primeiro_acesso,
)
from app.services.auth_service import (
    trocar_senha as service_trocar_senha,
)

router = APIRouter(prefix="/auth", tags=["autenticação"])


@router.post("/login")
def fazer_login(body: LoginIn, db: DbDep) -> ItemResponse[LoginOut]:
    token, expira, usuario = login(db, body.login, body.senha)
    return ItemResponse(
        data=LoginOut(
            token=token,
            expira_em=expira,
            usuario=UsuarioSessaoOut.model_validate(usuario),
        )
    )


@router.post("/primeiro-acesso", status_code=201)
def completar_primeiro_acesso(
    body: PrimeiroAcessoIn, db: DbDep
) -> ItemResponse[LoginOut]:
    """Completa o primeiro acesso: define senha e devolve token de sessão."""
    token, expira, usuario_obj = service_primeiro_acesso(
        db, login=body.login, nova_senha=body.nova_senha
    )
    return ItemResponse(
        data=LoginOut(
            token=token,
            expira_em=expira,
            usuario=UsuarioSessaoOut.model_validate(usuario_obj),
        )
    )


@router.post("/logout")
def fazer_logout(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    token = (authorization or "").removeprefix("Bearer ").strip()
    logout(db, token)
    return {"data": True}


@router.get("/me")
def quem_sou(usuario: UsuarioDep) -> ItemResponse[UsuarioSessaoOut]:
    return ItemResponse(data=UsuarioSessaoOut.model_validate(usuario))


@router.post("/trocar-senha")
def trocar_senha(
    body: TrocarSenhaIn,
    usuario: UsuarioDep,
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    token = (authorization or "").removeprefix("Bearer ").strip() or None
    service_trocar_senha(db, usuario, body.senha_atual, body.nova_senha, token)
    return {"data": True}
