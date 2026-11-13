"""Bootstrap inicial: empresa, filial e usuário administrador de fábrica.

Executado no startup do serviço e idempotente. **Multi-tenant**: com
`PRINTGEST_EMPRESA_CNPJ` no `.env`, o bootstrap garante a EMPRESA/FILIAL/ADMIN
daquele inquilino no banco compartilhado (duas gráficas coexistem no mesmo
banco, cada uma com seus dados isolados por `filial_id`). Sem a variável
(dev/demo), mantém o comportamento histórico da empresa demo
`11111111000111`.

Em instalações novas o admin nasce sem senha (`primeiro_acesso=True`) e o
operador define a dele na tela de primeiro acesso. Em dev/testes,
`PRINTGEST_ADMIN_INICIAL_PRIMEIRO_ACESSO=false` mantém a senha de fábrica de
`PRINTGEST_ADMIN_INICIAL_SENHA`.
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models.core import Empresa, Filial, Usuario
from app.models.enums import NivelAcesso


def _criar_empresa(db: Session, cnpj: str) -> Empresa:
    if cnpj == "11111111000111":
        empresa = Empresa(
            razao_social="Gráfica Demo Ltda",
            nome_fantasia="PrintGest",
            cnpj=cnpj,
            inscricao_estadual="ISENTO",
            regime_tributario="Simples Nacional",
            ambiente_fiscal="h",
            cidade="São Paulo",
            uf="SP",
        )
    else:
        empresa = Empresa(
            razao_social=settings.empresa_razao_social.strip() or f"Gráfica {cnpj}",
            cnpj=cnpj,
            inscricao_estadual="ISENTO",
            ambiente_fiscal="h",
        )
    db.add(empresa)
    db.flush()
    return empresa


def garantir_empresa(db: Session, cnpj: str) -> tuple[Empresa, Filial]:
    """Garante empresa + filial "Matriz" do CNPJ (multi-tenant).

    Usada pelo bootstrap (inquilino do `.env`/cofre) e pela primeira ativação
    (CNPJ digitado na tela de ativação — instalador universal).
    """
    empresa = db.query(Empresa).filter(Empresa.cnpj == cnpj).first()
    if not empresa:
        empresa = _criar_empresa(db, cnpj)
    filial = db.query(Filial).filter(Filial.empresa_id == empresa.id).first()
    if not filial:
        # A primeira unidade é a MATRIZ, não uma filial — o nome "Filial
        # Matriz" era contraditório na top bar (ou é matriz, ou é filial).
        filial = Filial(
            empresa_id=empresa.id,
            nome=(settings.empresa_filial_nome or "Matriz").strip() or "Matriz",
        )
        db.add(filial)
        db.flush()
    return empresa, filial


def _empresa() -> Empresa:
    db = SessionLocal()
    try:
        # Inquilino desta instalação: `.env` → cofre local (1ª ativação) → demo.
        from app.services import tenants

        cnpj = tenants.cnpj_do_tenant() or "11111111000111"
        empresa, filial = garantir_empresa(db, cnpj)
        # Multi-tenant: o MESMO login pode existir em inquilinos diferentes —
        # o admin buscado é o DENTRO das filiais desta empresa.
        admin = (
            db.query(Usuario)
            .join(Filial, Usuario.filial_id == Filial.id)
            .filter(Filial.empresa_id == empresa.id)
            .filter(Usuario.login == settings.admin_inicial_login)
            .first()
        )
        if not admin:
            primeiro_acesso = settings.admin_inicial_primeiro_acesso
            admin = Usuario(
                filial_id=filial.id,
                nome=settings.admin_inicial_nome,
                login=settings.admin_inicial_login,
                senha_hash=(
                    None
                    if primeiro_acesso
                    else hash_password(settings.admin_inicial_senha)
                ),
                primeiro_acesso=primeiro_acesso,
                nivel_acesso=NivelAcesso.ADMIN,
            )
            db.add(admin)
        db.commit()
        return empresa
    finally:
        db.close()


def rodar_bootstrap() -> Empresa:
    return _empresa()
