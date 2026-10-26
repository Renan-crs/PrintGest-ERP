"""Bootstrap inicial: empresa, filial e usuário administrador de fábrica.

Executado no startup do serviço e idempotente — só cria o que não existe
(busca por CNPJ fixo e login 'admin'). As senhas iniciais para dev vêm do
Settings (PRINTGEST_ADMIN_INICIAL_SENHA); em produção substituir via env.
"""

from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models.core import Empresa, Filial, Usuario
from app.models.enums import NivelAcesso


def _empresa() -> Empresa:
    db = SessionLocal()
    try:
        empresa = db.query(Empresa).filter(Empresa.cnpj == "11111111000111").first()
        if not empresa:
            empresa = Empresa(
                razao_social="Gráfica Demo Ltda",
                nome_fantasia="PrintGest",
                cnpj="11111111000111",
                inscricao_estadual="ISENTO",
                regime_tributario="Simples Nacional",
                ambiente_fiscal="h",
                cidade="São Paulo",
                uf="SP",
            )
            db.add(empresa)
            db.flush()
        filial = db.query(Filial).filter(Filial.empresa_id == empresa.id).first()
        if not filial:
            # A primeira unidade é a MATRIZ, não uma filial — o nome "Filial
            # Matriz" era contraditório na top bar (ou é matriz, ou é filial).
            filial = Filial(empresa_id=empresa.id, nome="Matriz")
            db.add(filial)
            db.flush()
        admin = db.query(Usuario).filter(Usuario.login == settings.admin_inicial_login).first()
        if not admin:
            admin = Usuario(
                filial_id=filial.id,
                nome=settings.admin_inicial_nome,
                login=settings.admin_inicial_login,
                senha_hash=hash_password(settings.admin_inicial_senha),
                nivel_acesso=NivelAcesso.ADMIN,
            )
            db.add(admin)
        db.commit()
        return empresa
    finally:
        db.close()


def rodar_bootstrap() -> Empresa:
    return _empresa()