from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.deps import DbDep, UsuarioDep
from app.schemas import ItemResponse, LoginIn, LoginOut, TrocarSenhaIn, UsuarioSessaoOut
from app.services.auth_service import login, logout, sessao_por_token
from app.core.security import hash_password, verify_password
from app.models.core import Usuario

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
) -> dict[str, bool]:
    if not verify_password(body.senha_atual, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta.",
        )
    usuario.senha_hash = hash_password(body.nova_senha)
    db.commit()
    return {"data": True}