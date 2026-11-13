"""Inquilino (tenant) da instalação no banco compartilhado.

O projeto Neon do PrintGest é ÚNICO e atende várias gráficas. O inquilino que
esta instalação (daemon) serve é a `empresa` do CNPJ — nesta ordem:

1. `PRINTGEST_EMPRESA_CNPJ` no `.env` (explícito; dev/instalador);
2. o CNPJ gravado no cofre local da máquina na primeira ativação
   (`cofre_maquina`, o mesmo arquivo de recuperação da licença) — é o que
   faz o **instalador universal** funcionar: o CNPJ é informado na tela de
   ativação do aplicativo (como a chave de produto do Office), não no
   instalador;
3. sem nenhum dos dois, modo single-tenant legado (dev/demo): todas as
   funções devolvem "sem escopo" e o comportamento é o de antes.
"""

from sqlalchemy.orm import Session

from app.core import cofre_maquina
from app.core.config import settings
from app.models.core import Empresa, Filial, Usuario


def cnpj_do_tenant() -> str:
    """CNPJ do inquilino ('' = single-tenant legado).

    Ordem: `.env` → cofre local da máquina (1ª ativação) → legado.
    """
    cnpj = (settings.empresa_cnpj or "").strip()
    if cnpj:
        return cnpj
    material = cofre_maquina.ler()
    return str(material.get("cnpj") or "").strip() if material else ""


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

    No modo legado, busca global — o `usuario.login` era globalmente único nas
    bases antigas.
    """
    consulta = db.query(Usuario).filter(Usuario.login == login)
    filiais = filiais_do_tenant(db)
    if filiais:
        consulta = consulta.filter(Usuario.filial_id.in_(filiais))
    return consulta.order_by(Usuario.id).first()
