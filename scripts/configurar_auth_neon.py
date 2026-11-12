#!/usr/bin/env python
"""Prepara o processo de autenticação no banco Neon (produção).

Executa, contra o banco apontado pelo arquivo de ambiente informado
(default: `backend/.env.neon`), a mesma sequência do startup do Local API
Service:

  1. carrega o `.env` informado (PRINTGEST_*) e roda `validar_producao()`
     (P17: recusa senha de fábrica/credencial de banco fora de dev);
  2. `alembic upgrade head` — cria/atualiza o schema (`usuario`,
     `usuario_sessao`, enum de nível, etc.), idempotente;
  3. bootstrap — cria empresa, filial e o admin de fábrica se não existirem;
  4. valida o estado do auth do admin: ativo, primeiro acesso, bloqueio e se
     a senha de fábrica confere com o hash gravado (sem criar sessão).

Uso:

    backend\\.venv\\Scripts\\python.exe scripts\\configurar_auth_neon.py
    backend\\.venv\\Scripts\\python.exe scripts\\configurar_auth_neon.py --env-file caminho\\.env

O script nunca imprime a senha nem a connection string.
"""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _carregar_env(arquivo: Path) -> dict[str, str]:
    """Lê `CHAVE=valor` (PRINTGEST_*) e devolve o dicionário; não imprime valores."""
    if not arquivo.exists():
        print(f"ERRO: arquivo de ambiente não encontrado: {arquivo}")
        sys.exit(1)
    valores: dict[str, str] = {}
    for linha in arquivo.read_text(encoding="utf-8", errors="ignore").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return {k: v for k, v in valores.items() if k.startswith("PRINTGEST_")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file",
        default=str(RAIZ / "backend" / ".env.neon"),
        help="arquivo de ambiente do banco (default: backend/.env.neon)",
    )
    args = parser.parse_args()

    valores = _carregar_env(Path(args.env_file))
    if not valores.get("PRINTGEST_DATABASE_URL"):
        print("ERRO: PRINTGEST_DATABASE_URL ausente no arquivo de ambiente.")
        return 1
    for chave, valor in valores.items():
        os.environ[chave] = valor

    BACKEND = RAIZ / "backend"
    sys.path.insert(0, str(BACKEND))

    from app.bootstrap import rodar_bootstrap
    from app.core.config import settings
    from app.core.migrations import aplicar_migrations
    from app.core.security import verify_password
    from app.db import SessionLocal
    from app.services import tenants

    # 1. Validação P17 (produção recusa senha de fábrica 'admin123' e credencial
    # de banco padrão).
    settings.validar_producao()
    print(f"[1/4] Ambiente '{settings.env}' validado (P17 ok).")

    # 2. Migrations idempotentes (cria/atualiza schema do auth no Neon).
    aplicar_migrations()
    print("[2/4] Migrations Alembic aplicadas (upgrade head).")

    # 3. Bootstrap idempotente (empresa, filial e admin de fábrica do inquilino).
    empresa = rodar_bootstrap()
    print(
        f"[3/4] Bootstrap ok — empresa '{empresa.razao_social}' "
        f"(CNPJ {empresa.cnpj})."
    )

    # 4. Validação do auth do admin (sem criar sessão, sem imprimir segredos).
    # Multi-tenant: o admin é o DENTRO do inquilino (mesmo login pode existir
    # em gráficas distintas do banco compartilhado).
    db = SessionLocal()
    try:
        admin = tenants.usuario_por_login(db, settings.admin_inicial_login)
        if not admin:
            print(
                f"[4/4] ERRO: admin '{settings.admin_inicial_login}' não existe "
                "após o bootstrap."
            )
            return 1
        if admin.senha_hash is None or admin.primeiro_acesso:
            estado = "primeiro acesso (login pedirá cadastro de senha)"
            senha_ok = None
        else:
            estado = "senha de fábrica definida"
            senha_ok = verify_password(
                settings.admin_inicial_senha, admin.senha_hash
            )
        agora = datetime.now(UTC)
        bloqueio_ativo = (
            admin.bloqueado_em is not None and admin.bloqueado_em > agora
        )
        bloqueado_txt = (
            f"bloqueado até {admin.bloqueado_em.isoformat()}"
            if bloqueio_ativo
            else "não bloqueado"
        )
        print(
            f"[4/4] Admin '{admin.login}' (id={admin.id}, "
            f"nível={admin.nivel_acesso.value}): ativo={admin.ativo}, "
            f"{estado}, {bloqueado_txt}"
            + (
                ""
                if senha_ok is None
                else f", senha de fábrica confere={senha_ok}"
            )
        )
        if not admin.ativo:
            print(
                "AVISO: admin desativado — reative-o (usuario.ativo=true) ou "
                "use scripts/reset_senha_admin.py para redefinir o acesso."
            )
            return 1
        if senha_ok is False:
            print(
                "AVISO: a senha gravada NÃO é a de PRINTGEST_ADMIN_INICIAL_SENHA "
                "(já foi trocada). Use scripts/reset_senha_admin.py --sim para "
                "voltar à senha do .env."
            )
            return 1
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
