#!/usr/bin/env python
"""Reseta a senha de um usuário (por padrão o admin de fábrica) para a senha
padrão da instalação — uso de suporte quando o operador perdeu o acesso.

O que o script faz com o usuário alvo:

  - grava `senha_hash` da senha informada (default: `PRINTGEST_ADMIN_INICIAL_SENHA`,
    hoje `admin123`);
  - limpa `primeiro_acesso`, `falhas_login` e `bloqueado_em` (destrava o login);
  - encerra todas as sessões ativas (P13/P16: quem redefine a credencial invalida
    os acessos abertos).

Com `--primeiro-acesso` o usuário volta ao estado de instalação nova: sem senha
(`senha_hash=NULL`, `primeiro_acesso=True`) e o próprio operador define a senha
na tela "Primeiro acesso" do login.

Uso (com o Postgres da instalação/dev no ar):

    backend\\.venv\\Scripts\\python.exe scripts\\reset_senha_admin.py --sim
    backend\\.venv\\Scripts\\python.exe scripts\\reset_senha_admin.py --login joao --sim

Sem `--sim` o script apenas mostra o que faria (dry-run).
"""

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.core import Usuario  # noqa: E402
from app.services.auth_service import revogar_sessoes  # noqa: E402

_ENVS_SEGUROS = {"dev", "local", "test"}


def _senha_padrao(args: argparse.Namespace) -> str:
    if args.senha:
        return args.senha
    return settings.admin_inicial_senha


def _recusar_senha_insegura(senha: str) -> None:
    """P17: fora de dev/local/test, não permite voltar à senha de fábrica."""
    if senha == "admin123" and settings.env.lower() not in _ENVS_SEGUROS:
        print(
            f"ERRO: env='{settings.env}' não permite a senha de fábrica 'admin123'. "
            "Informe --senha com uma senha forte."
        )
        sys.exit(1)


def _resetar(
    login: str,
    senha: str | None,
    primeiro_acesso: bool,
    confirmar: bool,
) -> int:
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.login == login).first()
        if not usuario:
            print(f"ERRO: usuário '{login}' não encontrado no banco.")
            return 1
        if not usuario.ativo:
            print(
                f"AVISO: usuário '{login}' está desativado (ativo=false); "
                "o reset não o reativa."
            )

        if primeiro_acesso:
            acao = "senha removida (voltará a pedir 'Primeiro acesso')"
        else:
            acao = f"senha -> {senha}"
        ativas = sum(1 for s in usuario.sessoes if not s.encerrada)
        verbo = "reset para" if confirmar else "seria: reset para"
        print(
            f"  usuario id={usuario.id} login={usuario.login} "
            f"nivel={usuario.nivel_acesso.value} sessoes_ativas={ativas} "
            f"-> {verbo} {acao} -> sessões encerradas"
        )

        if confirmar:
            usuario.senha_hash = None if primeiro_acesso else hash_password(senha)
            usuario.primeiro_acesso = primeiro_acesso
            usuario.falhas_login = 0
            usuario.bloqueado_em = None
            db.commit()
            revogar_sessoes(db, usuario.id)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--login",
        default=settings.admin_inicial_login,
        help=(
            "login do usuário a resetar "
            f"(default: {settings.admin_inicial_login})"
        ),
    )
    parser.add_argument(
        "--senha",
        default=None,
        help=(
            "nova senha (default: PRINTGEST_ADMIN_INICIAL_SENHA, "
            f"hoje '{settings.admin_inicial_senha}')"
        ),
    )
    parser.add_argument(
        "--primeiro-acesso",
        action="store_true",
        help="em vez de definir senha, volta o usuário ao estado de primeiro acesso",
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        help="confirma o reset (sem esta opção é apenas dry-run)",
    )
    args = parser.parse_args()

    senha_escolhida = None if args.primeiro_acesso else _senha_padrao(args)
    if senha_escolhida is not None:
        _recusar_senha_insegura(senha_escolhida)

    codigo = _resetar(
        login=args.login,
        senha=senha_escolhida,
        primeiro_acesso=args.primeiro_acesso,
        confirmar=args.sim,
    )
    if codigo != 0:
        sys.exit(codigo)
    if not args.sim:
        print("Dry-run: nada foi alterado. Repita com --sim para aplicar o reset.")
    else:
        print("OK. Faça login com a nova credencial.")
