"""Inquilino (tenant) da instalação no banco compartilhado.

O projeto Neon do PrintGest é ÚNICO e atende várias gráficas. O inquilino que
esta instalação (daemon) serve é a `empresa` declarada em
`PRINTGEST_EMPRESA_CNPJ` — o bootstrap garante empresa/filial/admin dela, o
login busca usuários dentro do inquilino e a licença é por inquilino
(`licenca.empresa_id`).

Sem `PRINTGEST_EMPRESA_CNPJ` (dev/demo), o sistema opera no modo single-tenant
legado: todas as funções aqui devolvem "sem escopo" e o comportamento é o de
antes (busca global).
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.core import Empresa, Filial, Usuario


def cnpj_do_tenant() -> str:
    """CNPJ do inquilino declarado no `.env` ('' = single-tenant legado)."""
    return (settings.empresa_cnpj or "").strip()


def _id_do_cnpj(db: Session, cnpj: str) -> int | None:
    return db.query(Empresa.id).filter(Empresa.cnpj == cnpj).scalar()


def empresa_id_do_tenant(db: Session) -> int | None:
    """`empresa.id` do inquilino; `None` quando sem inquilino configurado."""
    cnpj = cnpj_do_tenant()
    if not cnpj:
        return None
    return _id_do_cnpj(db, cnpj)


def filiais_do_tenant(db: Session) -> list[int]:
    """Ids das filiais do inquilino (`[]` no modo legado)."""
    empresa_id = empresa_id_do_tenant(db)
    if empresa_id is None:
        return []
    return [
        id_
        for (id_,) in db.query(Filial.id).filter(Filial.empresa_id == empresa_id).all()
    ]


def usuario_por_login(db: Session, login: str) -> Usuario | None:
    """Busca o usuário DENTRO do inquilino (mesmo login em gráficas distintas).

    No modo legado (sem `PRINTGEST_EMPRESA_CNPJ`), busca global — o
    `usuario.login` era globalmente único nas bases antigas.
    """
    consulta = db.query(Usuario).filter(Usuario.login == login)
    filiais = filiais_do_tenant(db)
    if filiais:
        consulta = consulta.filter(Usuario.filial_id.in_(filiais))
    return consulta.order_by(Usuario.id).first()
