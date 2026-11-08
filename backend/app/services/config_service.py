"""Serviços de Configuração (PRD §1.8 / telas_e_fluxos §1.8, §2.6).

- **Empresa / Personalização:** leitura e atualização parcial da tabela
  `empresa` (cadastro fiscal, endereço, contato, logotipo/fundo e impressoras).
- **Reajuste de Preços em Bloco:** o produto ganha uma **prévia** (`simular`) e
  só então um `aplicar` que exige a **senha** do admin, grava a trilha de
  auditoria em `preco_reajuste_historico` e é transacional por requisição.

Produtos com `bloqueado_reajuste` (schema.sql, §8.1) são **pulados**: a prévia os
conta em `bloqueados` e o `aplicar` não os toca.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.cadastros import Produto
from app.models.config import PrecoReajusteHistorico
from app.models.core import Empresa, Filial, Usuario

_DUAS_CASAS = Decimal("0.01")
_MAX_ITENS_PREVIA = 500


# --------------------------------------------------------------------- empresa
def empresa_atual(db: Session, *, filial_id: int) -> Empresa:
    """Empresa da filial informada (fallback para a primeira empresa ativa)."""
    filial = db.get(Filial, filial_id)
    empresa = None
    if filial is not None and filial.empresa_id:
        empresa = db.get(Empresa, filial.empresa_id)
    if empresa is None:
        empresa = (
            db.query(Empresa)
            .filter(Empresa.ativa.is_(True))
            .order_by(Empresa.id.asc())
            .first()
        )
    if empresa is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Empresa não cadastrada.",
        )
    return empresa


# Colunas NOT NULL de `empresa` (schema.sql): um `null` vindo da UI não pode
# apagá-las — o campo é simplesmente ignorado.
_CAMPOS_OBRIGATORIOS = {"razao_social", "cnpj", "ambiente_fiscal", "ativa"}


def atualizar_empresa(db: Session, *, filial_id: int, dados: dict) -> Empresa:
    empresa = empresa_atual(db, filial_id=filial_id)
    for chave, valor in dados.items():
        if valor is None and chave in _CAMPOS_OBRIGATORIOS:
            continue
        setattr(empresa, chave, valor)
    db.commit()
    db.refresh(empresa)
    return empresa


# -------------------------------------------------------------------- reajuste
def _rotulo_criterio(criterio: str, categoria_id: int | None) -> str:
    # Formato do schema.sql: 'todos' | 'categoria:<id>'.
    if criterio == "categoria":
        return f"categoria:{categoria_id}"
    return "todos"


def _produtos_da_selecao(
    db: Session, *, filial_id: int, criterio: str, categoria_id: int | None
) -> list[Produto]:
    query = db.query(Produto).filter(Produto.filial_id == filial_id)
    if criterio == "categoria":
        query = query.filter(Produto.categoria_id == categoria_id)
    return query.order_by(Produto.nome.asc(), Produto.id.asc()).all()


def _novo_preco(preco: Decimal, tipo: str, valor: Decimal) -> Decimal:
    if tipo == "percentual":
        novo = preco * (Decimal(1) + valor / Decimal(100))
    else:
        novo = preco + valor
    if novo < 0:
        novo = Decimal(0)
    return novo.quantize(_DUAS_CASAS, rounding=ROUND_HALF_UP)


def _validar(criterio: str, categoria_id: int | None) -> None:
    if criterio == "categoria" and categoria_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selecione a categoria do reajuste.",
        )


def simular(
    db: Session,
    *,
    filial_id: int,
    criterio: str,
    categoria_id: int | None,
    tipo_reajuste: str,
    valor: Decimal,
) -> dict:
    _validar(criterio, categoria_id)
    produtos = _produtos_da_selecao(
        db, filial_id=filial_id, criterio=criterio, categoria_id=categoria_id
    )
    itens: list[dict] = []
    bloqueados = 0
    for produto in produtos:
        if produto.bloqueado_reajuste:
            bloqueados += 1
            continue
        antes = Decimal(produto.preco_venda)
        itens.append(
            {
                "produto_id": produto.id,
                "codigo": produto.codigo,
                "nome": produto.nome,
                "preco_antes": antes,
                "preco_depois": _novo_preco(antes, tipo_reajuste, valor),
            }
        )
    return {
        "total": len(produtos),
        "afetados": len(itens),
        "bloqueados": bloqueados,
        "itens": itens[:_MAX_ITENS_PREVIA],
    }


def aplicar(
    db: Session,
    *,
    filial_id: int,
    usuario: Usuario,
    criterio: str,
    categoria_id: int | None,
    tipo_reajuste: str,
    valor: Decimal,
    senha: str,
) -> dict:
    _validar(criterio, categoria_id)
    # A senha é a do admin autenticado — não trafega nem é comparada em claro.
    if not verify_password(senha, usuario.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha incorreta. O reajuste não foi aplicado.",
        )

    produtos = _produtos_da_selecao(
        db, filial_id=filial_id, criterio=criterio, categoria_id=categoria_id
    )
    elegiveis = [p for p in produtos if not p.bloqueado_reajuste]
    if not elegiveis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum produto elegível para o reajuste.",
        )

    detalhes: list[dict] = []
    for produto in elegiveis:
        antes = Decimal(produto.preco_venda)
        depois = _novo_preco(antes, tipo_reajuste, valor)
        produto.preco_venda = depois
        detalhes.append(
            {
                "produto_id": produto.id,
                "codigo": produto.codigo,
                "nome": produto.nome,
                "preco_antes": str(antes),
                "preco_depois": str(depois),
            }
        )

    historico = PrecoReajusteHistorico(
        filial_id=filial_id,
        usuario_id=usuario.id,
        tipo_reajuste=tipo_reajuste,
        valor_reajuste=valor,
        criterio=_rotulo_criterio(criterio, categoria_id),
        itens_afetados=len(elegiveis),
        detalhes=detalhes,
    )
    db.add(historico)
    db.commit()
    db.refresh(historico)
    return {
        "historico_id": historico.id,
        "afetados": historico.itens_afetados,
        "executado_em": historico.executado_em,
    }


def listar_historico(
    db: Session, *, filial_id: int, limit: int = 20, offset: int = 0
) -> tuple[list[PrecoReajusteHistorico], int]:
    query = db.query(PrecoReajusteHistorico).filter(
        PrecoReajusteHistorico.filial_id == filial_id
    )
    total = query.count()
    itens = (
        query.order_by(
            PrecoReajusteHistorico.executado_em.desc(),
            PrecoReajusteHistorico.id.desc(),
        )
        .limit(limit)
        .offset(offset)
        .all()
    )
    return itens, total
