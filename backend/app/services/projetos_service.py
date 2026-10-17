"""Serviços do módulo Projetos (PRD Módulo Projetos — Quadro Kanban).

Camada de regra de negócio do quadro. Três eixos:

- **Ordenação fracionária (§10).** `posicao` guarda um número racional para
  inserir no meio sem renumerar a coluna. A API expõe um **índice** (0-based);
  aqui o índice vira fração e, quando o passo se esgota, a lista é rebalanceada
  com passo uniforme.
- **Visibilidade (PV1–PV5).** Um único predicado (`_condicao_visivel`) é
  aplicado em toda consulta — quadro, lista, busca, contagem, obter e mover.
  Cartão invisível devolve 404, nunca 403, para não confirmar existência (PV2).
- **Sincronização de membros (PV3/PV4).** Lista pessoal adiciona o dono como
  membro de origem `lista`; atribuir a outro usuário restringe o cartão e, para
  quem não é gestor, o atribuidor vira acompanhante.

A sincronização com o status da O.S. (RN2) fica na **fase 5** (vínculo com OS);
as colunas `ordem_servico_id` e `status_os` já existem para recebê-la.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, true
from sqlalchemy.orm import Session

from app.models.core import Usuario
from app.models.enums import NivelAcesso, OrigemMembro, StatusOs, TipoLista
from app.models.projetos import (
    PASSO_FRACIONARIO,
    Cartao,
    CartaoMembro,
    Quadro,
    QuadroLista,
)

# Precisão das colunas `posicao` (Numeric(24, 12)) — arredonda antes de comparar.
_PRECISAO = Decimal("0.000000000001")
_GESTORES = (NivelAcesso.ADMIN, NivelAcesso.GERENTE)

# Listas iniciais (§4.1 + decisão D4): seed do spec até o responsável informar
# os nomes reais do quadro. `status_os` define o mapeamento com a O.S. (RN2).
_LISTAS_SEED: tuple[tuple[str, TipoLista, StatusOs], ...] = (
    ("Orçamento", TipoLista.ORCAMENTO, StatusOs.ABERTO),
    ("Aguardando", TipoLista.APROVACAO, StatusOs.APROVADO),
    ("Em produção", TipoLista.PRODUCAO, StatusOs.PRODUCAO),
    ("Pronta", TipoLista.FINAL, StatusOs.PRONTA),
    ("Entregue", TipoLista.FINAL, StatusOs.ENTREGUE),
)


class _EspacoEsgotado(Exception):
    """Sem passo fracionário entre duas posições — exige rebalanceamento."""


def _nao_encontrado() -> HTTPException:
    # Invisível e inexistente devolvem o mesmo 404 (PV2): sem confirmação.
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Registro não encontrado."
    )


# --------------------------------------------------------------- visibilidade


def _condicao_visivel(db: Session, usuario: Usuario):
    """PV1 (equipe) + PV2 (exclusividade por membros) — predicado único.

    Sem membros o cartão é da equipe; havendo ao menos um, restringe-se aos
    membros e aos cargos de gestão. A visibilidade é derivada de `cartao_membro`
    e nunca armazenada.
    """
    if usuario.nivel_acesso in _GESTORES:
        return true()
    restrito = (
        db.query(CartaoMembro)
        .filter(CartaoMembro.cartao_id == Cartao.id)
        .exists()
    )
    sou_membro = (
        db.query(CartaoMembro)
        .filter(
            CartaoMembro.cartao_id == Cartao.id,
            CartaoMembro.usuario_id == usuario.id,
        )
        .exists()
    )
    return or_(~restrito, sou_membro)


def _buscar_cartao(db: Session, usuario: Usuario, cartao_id: int, filial_id: int) -> Cartao:
    cartao = (
        db.query(Cartao)
        .filter(
            Cartao.id == cartao_id,
            Cartao.filial_id == filial_id,
            _condicao_visivel(db, usuario),
        )
        .first()
    )
    if cartao is None:
        raise _nao_encontrado()
    return cartao


def _e_gestor(usuario: Usuario) -> bool:
    return usuario.nivel_acesso in _GESTORES


# --------------------------------------------------------------------- quadro


def obter_quadro(db: Session, filial_id: int) -> Quadro:
    """Quadro da filial, criando-o com as listas-seed na primeira consulta.

    A semente é idempotente e necessária para o quadro renderizar; como a
    migração do módulo é aditiva, ela roda sob um GET (o modo de leitura da
    licença só bloqueia escritas de negócio, não a estrutura do quadro).
    """
    quadro = db.query(Quadro).filter(Quadro.filial_id == filial_id).first()
    if quadro is None:
        quadro = Quadro(filial_id=filial_id, nome="Projetos")
        db.add(quadro)
        db.flush()
        for indice, (nome, tipo, status_os) in enumerate(_LISTAS_SEED, start=1):
            db.add(
                QuadroLista(
                    quadro_id=quadro.id,
                    nome=nome,
                    tipo=tipo,
                    status_os=status_os,
                    posicao=PASSO_FRACIONARIO * indice,
                )
            )
        db.commit()
        db.refresh(quadro)
    return quadro


def _listas_ativas(db: Session, quadro: Quadro) -> list[QuadroLista]:
    return (
        db.query(QuadroLista)
        .filter(
            QuadroLista.quadro_id == quadro.id,
            QuadroLista.arquivada.is_(False),
        )
        .order_by(QuadroLista.posicao.asc())
        .all()
    )


def _contagens(db: Session, usuario: Usuario, quadro: Quadro) -> dict[int, int]:
    """PV5: contagem por lista respeitando a visibilidade do consultante."""
    linhas = (
        db.query(Cartao.lista_id, func.count(Cartao.id))
        .filter(
            Cartao.filial_id == quadro.filial_id,
            Cartao.arquivado.is_(False),
            _condicao_visivel(db, usuario),
        )
        .group_by(Cartao.lista_id)
        .all()
    )
    return {lista_id: total for lista_id, total in linhas}


def _nomes_usuarios(db: Session, ids) -> dict[int, str]:
    limpos = {i for i in ids if i is not None}
    if not limpos:
        return {}
    linhas = (
        db.query(Usuario.id, Usuario.nome).filter(Usuario.id.in_(limpos)).all()
    )
    return {i: nome for i, nome in linhas}


def _para_lista(
    lista: QuadroLista, contagem: int, donos: dict[int, str]
) -> dict:
    return {
        "id": lista.id,
        "quadro_id": lista.quadro_id,
        "nome": lista.nome,
        "posicao": lista.posicao,
        "tipo": lista.tipo,
        "status_os": lista.status_os,
        "usuario_dono_id": lista.usuario_dono_id,
        "usuario_dono_nome": donos.get(lista.usuario_dono_id),
        "fornecedor_id": lista.fornecedor_id,
        "arquivada": lista.arquivada,
        "contagem": contagem,
    }


def _lista_out(db: Session, usuario: Usuario, quadro: Quadro, lista: QuadroLista) -> dict:
    """Saída de lista com dono nomeado e contagem real (PV5) — usada nas
    respostas de criar/atualizar/arquivar, que senão devolveriam `contagem: 0`
    e dono anônimo.
    """
    contagens = _contagens(db, usuario, quadro)
    donos = _nomes_usuarios(db, [lista.usuario_dono_id])
    return _para_lista(lista, contagens.get(lista.id, 0), donos)


def quadro_out(db: Session, usuario: Usuario, quadro: Quadro) -> dict:
    listas = _listas_ativas(db, quadro)
    contagens = _contagens(db, usuario, quadro)
    donos = _nomes_usuarios(db, [l.usuario_dono_id for l in listas])
    return {
        "id": quadro.id,
        "filial_id": quadro.filial_id,
        "nome": quadro.nome,
        "listas": [_para_lista(l, contagens.get(l.id, 0), donos) for l in listas],
    }


# ----------------------------------------------------------------- ordenação


def _posicoes_cartao(db: Session, lista_id: int, exceto_id: int | None = None):
    q = db.query(Cartao.posicao).filter(
        Cartao.lista_id == lista_id, Cartao.arquivado.is_(False)
    )
    if exceto_id is not None:
        q = q.filter(Cartao.id != exceto_id)
    return [p for (p,) in q.order_by(Cartao.posicao.asc()).all()]


def _posicoes_lista(db: Session, quadro_id: int, exceto_id: int | None = None):
    q = db.query(QuadroLista.posicao).filter(
        QuadroLista.quadro_id == quadro_id, QuadroLista.arquivada.is_(False)
    )
    if exceto_id is not None:
        q = q.filter(QuadroLista.id != exceto_id)
    return [p for (p,) in q.order_by(QuadroLista.posicao.asc()).all()]


def _posicao_para_indice(posicoes: list[Decimal], indice: int) -> Decimal:
    """Converte o índice de destino na fração correspondente (§10)."""
    indice = max(0, min(indice, len(posicoes)))
    anterior = posicoes[indice - 1] if indice > 0 else None
    proxima = posicoes[indice] if indice < len(posicoes) else None
    if anterior is None and proxima is None:
        return PASSO_FRACIONARIO
    if anterior is None:
        return proxima - PASSO_FRACIONARIO
    if proxima is None:
        return anterior + PASSO_FRACIONARIO
    meio = ((anterior + proxima) / 2).quantize(_PRECISAO)
    if meio <= anterior or meio >= proxima:
        raise _EspacoEsgotado()
    return meio


def _rebalancear_cartoes(db: Session, lista_id: int) -> None:
    linhas = (
        db.query(Cartao)
        .filter(Cartao.lista_id == lista_id, Cartao.arquivado.is_(False))
        .order_by(Cartao.posicao.asc())
        .all()
    )
    for indice, cartao in enumerate(linhas, start=1):
        cartao.posicao = PASSO_FRACIONARIO * indice
    db.flush()


def _rebalancear_listas(db: Session, quadro_id: int) -> None:
    linhas = (
        db.query(QuadroLista)
        .filter(QuadroLista.quadro_id == quadro_id, QuadroLista.arquivada.is_(False))
        .order_by(QuadroLista.posicao.asc())
        .all()
    )
    for indice, lista in enumerate(linhas, start=1):
        lista.posicao = PASSO_FRACIONARIO * indice
    db.flush()


# --------------------------------------------------------------------- membros


def _garantir_membro(
    db: Session, cartao_id: int, usuario_id: int, origem: OrigemMembro, por: int | None
) -> None:
    """Adiciona o membro se ainda não for membro (mantém a origem existente)."""
    existe = (
        db.query(CartaoMembro)
        .filter(
            CartaoMembro.cartao_id == cartao_id,
            CartaoMembro.usuario_id == usuario_id,
        )
        .first()
    )
    if existe is None:
        db.add(
            CartaoMembro(
                cartao_id=cartao_id,
                usuario_id=usuario_id,
                origem=origem,
                adicionado_por=por,
            )
        )
        db.flush()


def _sincronizar_membro_lista(
    db: Session, cartao: Cartao, lista: QuadroLista, usuario: Usuario
) -> None:
    """PV3(b): lista pessoal adiciona o dono como membro (origem `lista`).

    Ao sair da lista pessoal, remove-se apenas a marcação de origem `lista` —
    membros manuais ou de atribuição permanecem.
    """
    dono = lista.usuario_dono_id if lista.tipo == TipoLista.USUARIO else None
    excluir = db.query(CartaoMembro).filter(
        CartaoMembro.cartao_id == cartao.id,
        CartaoMembro.origem == OrigemMembro.LISTA,
    )
    if dono is not None:
        excluir = excluir.filter(CartaoMembro.usuario_id != dono)
    excluir.delete(synchronize_session=False)
    if dono is not None:
        _garantir_membro(db, cartao.id, dono, OrigemMembro.LISTA, usuario.id)


def _membros_out(db: Session, cartao_id: int) -> list[dict]:
    linhas = (
        db.query(CartaoMembro, Usuario.nome)
        .join(Usuario, CartaoMembro.usuario_id == Usuario.id)
        .filter(CartaoMembro.cartao_id == cartao_id)
        .order_by(CartaoMembro.adicionado_em.asc())
        .all()
    )
    return [
        {"usuario_id": m.usuario_id, "nome": nome, "origem": m.origem}
        for m, nome in linhas
    ]


def _para_cartao(db: Session, cartao: Cartao) -> dict:
    dados = {c.name: getattr(cartao, c.name) for c in Cartao.__table__.columns}
    donos = _nomes_usuarios(db, [cartao.ultimo_responsavel_id])
    dados["ultimo_responsavel_nome"] = donos.get(cartao.ultimo_responsavel_id)
    dados["membros"] = _membros_out(db, cartao.id)
    return dados


# ------------------------------------------------------------------- verções


def _verificar_versao(cartao: Cartao, versao: int) -> None:
    if versao != cartao.versao:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O cartão foi alterado por outro usuário. "
                "Recarregue e tente novamente."
            ),
        )


def _buscar_lista(db: Session, quadro: Quadro, lista_id: int) -> QuadroLista:
    lista = (
        db.query(QuadroLista)
        .filter(QuadroLista.id == lista_id, QuadroLista.quadro_id == quadro.id)
        .first()
    )
    if lista is None:
        raise _nao_encontrado()
    return lista


def _buscar_usuario_ativo(db: Session, usuario_id: int, filial_id: int) -> Usuario:
    alvo = (
        db.query(Usuario)
        .filter(Usuario.id == usuario_id, Usuario.ativo.is_(True))
        .first()
    )
    if alvo is None or (alvo.filial_id not in (None, filial_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário inativo ou de outra filial.",
        )
    return alvo


# -------------------------------------------------------------------- cartões


def listar_cartoes(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    q: str | None = None,
    lista_id: int | None = None,
    arquivado: bool = False,
    sou_membro: bool | None = None,
    limit: int = 500,
    offset: int = 0,
) -> tuple[list[dict], int]:
    base = db.query(Cartao).filter(
        Cartao.filial_id == filial_id,
        Cartao.arquivado.is_(arquivado),
        _condicao_visivel(db, usuario),
    )
    if lista_id is not None:
        base = base.filter(Cartao.lista_id == lista_id)
    termo = (q or "").strip()
    if termo:
        base = base.filter(
            or_(
                Cartao.titulo.ilike(f"%{termo}%"),
                Cartao.descricao.ilike(f"%{termo}%"),
            )
        )
    if sou_membro is True:
        base = base.filter(
            db.query(CartaoMembro)
            .filter(
                CartaoMembro.cartao_id == Cartao.id,
                CartaoMembro.usuario_id == usuario.id,
            )
            .exists()
        )
    total = base.count()
    linhas = (
        base.order_by(Cartao.lista_id.asc(), Cartao.posicao.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [_para_cartao(db, c) for c in linhas], total


def obter_cartao(db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int) -> dict:
    return _para_cartao(db, _buscar_cartao(db, usuario, cartao_id, filial_id))


def criar_cartao(
    db: Session, *, usuario: Usuario, filial_id: int, dados: dict
) -> dict:
    quadro = obter_quadro(db, filial_id)
    lista = _buscar_lista(db, quadro, dados["lista_id"])
    if lista.arquivada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível criar cartão em lista arquivada.",
        )
    posicoes = _posicoes_cartao(db, lista.id)
    cartao = Cartao(
        filial_id=filial_id,
        lista_id=lista.id,
        posicao=_posicao_para_indice(posicoes, len(posicoes)),
        titulo=dados["titulo"],
        descricao=dados.get("descricao"),
        data_inicio=dados.get("data_inicio"),
        data_entrega=dados.get("data_entrega"),
        lembrete_min=dados.get("lembrete_min"),
        criado_por=usuario.id,
    )
    db.add(cartao)
    db.flush()
    _sincronizar_membro_lista(db, cartao, lista, usuario)
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def atualizar_cartao(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, dados: dict
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    _verificar_versao(cartao, dados["versao"])
    # `exclude_unset` no router: campo ausente = não mexer; campo presente com
    # `null` = limpar (permite remover título nulo? não; limpa datas/descrição e
    # lembrete — edição parcial de verdade). `titulo` é não-nulo no schema.
    for campo in ("titulo", "descricao", "data_inicio", "data_entrega", "lembrete_min"):
        if campo in dados and not (campo == "titulo" and dados[campo] is None):
            setattr(cartao, campo, dados[campo])
    if dados.get("concluido") is not None:  # RN4: marca e desmarca sem bloquear
        cartao.concluido = bool(dados["concluido"])
        cartao.concluido_em = datetime.now(timezone.utc) if cartao.concluido else None
    cartao.versao += 1
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def mover_cartao(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    lista_id: int,
    indice: int,
    versao: int,
) -> dict:
    """MOVE atômico (§10): lista + posição + membros + versão numa transação."""
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    _verificar_versao(cartao, versao)
    quadro = obter_quadro(db, filial_id)
    destino = _buscar_lista(db, quadro, lista_id)
    if destino.arquivada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível mover cartão para lista arquivada.",
        )

    posicoes = _posicoes_cartao(db, destino.id, exceto_id=cartao.id)
    try:
        nova_posicao = _posicao_para_indice(posicoes, indice)
    except _EspacoEsgotado:
        _rebalancear_cartoes(db, destino.id)
        posicoes = _posicoes_cartao(db, destino.id, exceto_id=cartao.id)
        nova_posicao = _posicao_para_indice(posicoes, indice)

    cartao.lista_id = destino.id
    cartao.posicao = nova_posicao
    cartao.versao += 1
    _sincronizar_membro_lista(db, cartao, destino, usuario)
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def arquivar_cartao(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, versao: int
) -> dict:
    """RN6: arquivamento (não exclusão). Restauração por `restaurar_cartao`."""
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    _verificar_versao(cartao, versao)
    cartao.arquivado = True
    cartao.versao += 1
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def restaurar_cartao(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, versao: int
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    _verificar_versao(cartao, versao)
    cartao.arquivado = False
    cartao.versao += 1
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def atribuir_cartao(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, usuario_id: int, versao: int
) -> dict:
    """WF2/PV4: atribui a um usuário e restringe o cartão a ele.

    Para quem não é gestor, o atribuidor mantém acesso como acompanhante
    (origem `atribuidor`) — o cartão não fica órfão.
    """
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    _verificar_versao(cartao, versao)
    alvo = _buscar_usuario_ativo(db, usuario_id, filial_id)
    cartao.ultimo_responsavel_id = alvo.id
    _garantir_membro(db, cartao.id, alvo.id, OrigemMembro.MANUAL, usuario.id)
    if not _e_gestor(usuario) and usuario.id != alvo.id:
        _garantir_membro(db, cartao.id, usuario.id, OrigemMembro.ATRIBUIDOR, usuario.id)
    cartao.versao += 1
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def adicionar_membro(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, membro_id: int
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    _buscar_usuario_ativo(db, membro_id, filial_id)
    _garantir_membro(db, cartao.id, membro_id, OrigemMembro.MANUAL, usuario.id)
    cartao.versao += 1
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def remover_membro(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, membro_id: int
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    db.query(CartaoMembro).filter(
        CartaoMembro.cartao_id == cartao.id,
        CartaoMembro.usuario_id == membro_id,
    ).delete(synchronize_session=False)
    cartao.versao += 1
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


# -------------------------------------------------------------------- listas


def criar_lista(
    db: Session, *, usuario: Usuario, quadro: Quadro, dados: dict
) -> dict:
    indice = dados.get("posicao")
    posicoes = _posicoes_lista(db, quadro.id)
    if indice is None:
        indice = len(posicoes)
    lista = QuadroLista(
        quadro_id=quadro.id,
        nome=dados["nome"],
        tipo=dados.get("tipo", TipoLista.LIVRE),
        status_os=dados.get("status_os"),
        usuario_dono_id=dados.get("usuario_dono_id"),
        fornecedor_id=dados.get("fornecedor_id"),
        posicao=_posicao_para_indice(posicoes, indice),
    )
    db.add(lista)
    db.commit()
    db.refresh(lista)
    return _lista_out(db, usuario, quadro, lista)


def atualizar_lista(
    db: Session, *, usuario: Usuario, quadro: Quadro, lista_id: int, dados: dict
) -> dict:
    lista = _buscar_lista(db, quadro, lista_id)
    for campo in ("nome", "tipo", "status_os", "usuario_dono_id", "fornecedor_id"):
        if campo in dados and dados[campo] is not None:
            setattr(lista, campo, dados[campo])
    if dados.get("posicao") is not None:
        _reordenar_lista(db, quadro, lista, dados["posicao"])
    db.commit()
    db.refresh(lista)
    return _lista_out(db, usuario, quadro, lista)


def _reordenar_lista(db: Session, quadro: Quadro, lista: QuadroLista, indice: int) -> None:
    posicoes = _posicoes_lista(db, quadro.id, exceto_id=lista.id)
    try:
        lista.posicao = _posicao_para_indice(posicoes, indice)
    except _EspacoEsgotado:
        _rebalancear_listas(db, quadro.id)
        posicoes = _posicoes_lista(db, quadro.id, exceto_id=lista.id)
        lista.posicao = _posicao_para_indice(posicoes, indice)


def arquivar_lista(
    db: Session, *, usuario: Usuario, quadro: Quadro, lista_id: int
) -> dict:
    """RN6: listas são arquivadas (os cartões seguem existindo, não somem)."""
    lista = _buscar_lista(db, quadro, lista_id)
    lista.arquivada = True
    db.commit()
    db.refresh(lista)
    return _lista_out(db, usuario, quadro, lista)


def excluir_lista(db: Session, *, usuario: Usuario, quadro: Quadro, lista_id: int) -> None:
    """Exclusão definitiva (Admin, §RN6): exige lista vazia de cartões."""
    lista = _buscar_lista(db, quadro, lista_id)
    ocupados = (
        db.query(func.count(Cartao.id))
        .filter(Cartao.lista_id == lista.id, Cartao.arquivado.is_(False))
        .scalar()
        or 0
    )
    if ocupados:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mova ou arquive os cartões antes de excluir a lista.",
        )
    db.delete(lista)
    db.commit()
