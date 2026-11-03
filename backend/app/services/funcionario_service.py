"""Serviço de Funcionário (PRD v3.0 §3.10 - primeiro acesso).

Quando um funcionário é cadastrado pelo admin, o sistema cria automaticamente
uma conta de usuário com login e flag de primeiro acesso. No primeiro login,
o funcionário deve definir sua senha.
"""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cadastros import Funcionario
from app.models.core import Usuario


def criar_com_usuario(
    db: Session, modelo_funcionario: type[Funcionario], dados: dict[str, Any]
) -> Funcionario:
    """Cria funcionário e usuário vinculado (M3 §3.10)."""
    login = dados.pop("login", None)
    if not login:
        raise ValueError("O campo 'login' é obrigatório para cadastro de funcionário.")

    funcionario = modelo_funcionario(**dados)
    db.add(funcionario)
    try:
        db.flush()  # Garante que funcionario.id existe

        usuario = Usuario(
            nome=dados.get("nome"),
            login=login,
            senha_hash=None,  # Primeiro acesso: senha será definida no login
            primeiro_acesso=True,  # Flag para pedir senha no primeiro login
            nivel_acesso="operador",
            funcionario_id=funcionario.id,
            filial_id=dados.get("filial_id"),
            email=dados.get("email"),
        )
        db.add(usuario)
        db.flush()
        # Link reverso (Funcionario.usuario_id) — mantém as duas pontas coerentes
        # e evita `Funcionario.usuario` sempre nulo.
        funcionario.usuario_id = usuario.id
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dados duplicados: já existe um registro com esses valores.",
        ) from exc
    db.refresh(funcionario)
    return funcionario