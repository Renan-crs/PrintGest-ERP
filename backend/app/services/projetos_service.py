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

A **Fase 2** (cartão rico) acrescenta, no fim do arquivo: etiquetas aplicadas ao
cartão (RF10), checklists com itens ordenáveis por fração (RF11), comentários
com resposta em 1 nível e soft-delete (RF14) e o log de atividade append-only
(§12). Todas as sub-rotinas passam pelo `_buscar_cartao` (logo, por PV1–PV5) e
**nenhuma** incrementa `versao` — a versão otimista guarda texto/datas, mover,
arquivar e atribuir.

A sincronização com o status da O.S. (RN2) fica na **fase 5** (vínculo com OS);
as colunas `ordem_servico_id` e `status_os` já existem para recebê-la.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, true
from sqlalchemy.orm import Session

from app.models.core import Usuario
from app.models.enums import NivelAcesso, OrigemMembro, StatusOs, TipoLista
from app.models.projetos import (
    PASSO_FRACIONARIO,
    Cartao,
    CartaoAtividade,
    CartaoChecklist,
    CartaoChecklistItem,
    CartaoComentario,
    CartaoEtiqueta,
    CartaoMembro,
    Etiqueta,
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
        db.query(CartaoMembro).filter(CartaoMembro.cartao_id == Cartao.id).exists()
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


def _buscar_cartao(
    db: Session, usuario: Usuario, cartao_id: int, filial_id: int
) -> Cartao:
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
    linhas = db.query(Usuario.id, Usuario.nome).filter(Usuario.id.in_(limpos)).all()
    return {i: nome for i, nome in linhas}


def _para_lista(lista: QuadroLista, contagem: int, donos: dict[int, str]) -> dict:
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


def _lista_out(
    db: Session, usuario: Usuario, quadro: Quadro, lista: QuadroLista
) -> dict:
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
    # Fase 2 (RF4): etiquetas aplicadas e selos de progresso do cartão. Como o
    # `_membros_out` já faz isso, são consultas por cartão — a Fase 1 otimizou
    # a leitura em bloco só para listas/contagens; o resto é previsível no MVP.
    dados["etiquetas"] = _etiquetas_do_cartao(db, cartao.id)
    dados["checklist_total"], dados["checklist_concluidos"] = _progresso_checklists(
        db, cartao.id
    )
    dados["comentarios_total"] = _comentarios_contados(db, cartao.id)
    return dados


# ------------------------------------------------------------------- verções


def _verificar_versao(cartao: Cartao, versao: int) -> None:
    if versao != cartao.versao:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O cartão foi alterado por outro usuário. Recarregue e tente novamente."
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


def obter_cartao(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int
) -> dict:
    return _para_cartao(db, _buscar_cartao(db, usuario, cartao_id, filial_id))


def criar_cartao(db: Session, *, usuario: Usuario, filial_id: int, dados: dict) -> dict:
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
    _registrar_atividade(db, cartao.id, usuario.id, "criado", {"titulo": cartao.titulo})
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
    alterados: list[str] = []
    for campo in ("titulo", "descricao", "data_inicio", "data_entrega", "lembrete_min"):
        if campo in dados and not (campo == "titulo" and dados[campo] is None):
            if getattr(cartao, campo) != dados[campo]:
                alterados.append(campo)
            setattr(cartao, campo, dados[campo])
    concluido_antes = cartao.concluido
    if dados.get("concluido") is not None:  # RN4: marca e desmarca sem bloquear
        cartao.concluido = bool(dados["concluido"])
        cartao.concluido_em = datetime.now(UTC) if cartao.concluido else None
    if alterados:
        _registrar_atividade(
            db, cartao.id, usuario.id, "atualizado", {"campos": alterados}
        )
    if dados.get("concluido") is not None and cartao.concluido != concluido_antes:
        _registrar_atividade(
            db,
            cartao.id,
            usuario.id,
            "concluido" if cartao.concluido else "reaberto",
        )
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

    lista_anterior = cartao.lista_id
    cartao.lista_id = destino.id
    cartao.posicao = nova_posicao
    cartao.versao += 1
    _sincronizar_membro_lista(db, cartao, destino, usuario)
    _registrar_atividade(
        db,
        cartao.id,
        usuario.id,
        "movido",
        {"lista_origem": lista_anterior, "lista_destino": destino.id},
    )
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
    _registrar_atividade(db, cartao.id, usuario.id, "arquivado")
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
    _registrar_atividade(db, cartao.id, usuario.id, "restaurado")
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


def atribuir_cartao(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    usuario_id: int,
    versao: int,
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
    _registrar_atividade(
        db, cartao.id, usuario.id, "atribuido", {"usuario_id": alvo.id}
    )
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
    _registrar_atividade(
        db, cartao.id, usuario.id, "membro_add", {"usuario_id": membro_id}
    )
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
    _registrar_atividade(
        db, cartao.id, usuario.id, "membro_remove", {"usuario_id": membro_id}
    )
    db.commit()
    db.refresh(cartao)
    return _para_cartao(db, cartao)


# -------------------------------------------------------------------- listas


def criar_lista(db: Session, *, usuario: Usuario, quadro: Quadro, dados: dict) -> dict:
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


def _reordenar_lista(
    db: Session, quadro: Quadro, lista: QuadroLista, indice: int
) -> None:
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


def excluir_lista(
    db: Session, *, usuario: Usuario, quadro: Quadro, lista_id: int
) -> None:
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


# ============================================ Fase 2 — Cartão rico (RF10–RF14)
#
# Etiquetas, checklists, comentários e atividade (RF14/§12). Tudo passa pelo
# `_buscar_cartao`, então herda PV1–PV5 (cartão invisível → 404). Estas
# **sub-rotinas não incrementam `versao`**: a versão otimista guarda o texto do
# cartão (`PATCH /cartoes/{id}`), mover, arquivar e atribuir; etiquetas,
# checklists e comentários são recursos próprios e não invalidam a ficha aberta.


def _registrar_atividade(
    db: Session,
    cartao_id: int,
    usuario_id: int | None,
    tipo: str,
    dados: dict | None = None,
) -> None:
    """Anexa um evento ao log append-only (§12). O commit é de quem chama."""
    db.add(
        CartaoAtividade(
            cartao_id=cartao_id,
            usuario_id=usuario_id,
            tipo=tipo,
            dados=dados,
        )
    )


def listar_atividade(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int
) -> list[dict]:
    """Log do cartão, mais recente primeiro (limite de 200 eventos)."""
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    linhas = (
        db.query(CartaoAtividade)
        .filter(CartaoAtividade.cartao_id == cartao.id)
        .order_by(CartaoAtividade.criado_em.desc(), CartaoAtividade.id.desc())
        .limit(200)
        .all()
    )
    nomes = _nomes_usuarios(db, [a.usuario_id for a in linhas])
    return [
        {
            "id": a.id,
            "cartao_id": a.cartao_id,
            "usuario_id": a.usuario_id,
            "usuario_nome": nomes.get(a.usuario_id),
            "tipo": a.tipo,
            "dados": a.dados,
            "criado_em": a.criado_em,
        }
        for a in linhas
    ]


# ---------------------------------------------------------- Fase 2: etiquetas


def _etiqueta_dict(etiqueta: Etiqueta) -> dict:
    return {
        "id": etiqueta.id,
        "filial_id": etiqueta.filial_id,
        "nome": etiqueta.nome,
        "cor": etiqueta.cor,
    }


def listar_etiquetas(db: Session, filial_id: int) -> list[dict]:
    linhas = (
        db.query(Etiqueta)
        .filter(Etiqueta.filial_id == filial_id)
        .order_by(Etiqueta.criado_em.asc(), Etiqueta.id.asc())
        .all()
    )
    return [_etiqueta_dict(e) for e in linhas]


def criar_etiqueta(db: Session, *, filial_id: int, dados: dict) -> dict:
    etiqueta = Etiqueta(
        filial_id=filial_id, nome=dados.get("nome") or None, cor=dados["cor"]
    )
    db.add(etiqueta)
    db.commit()
    db.refresh(etiqueta)
    return _etiqueta_dict(etiqueta)


def _buscar_etiqueta(db: Session, filial_id: int, etiqueta_id: int) -> Etiqueta:
    etiqueta = (
        db.query(Etiqueta)
        .filter(Etiqueta.id == etiqueta_id, Etiqueta.filial_id == filial_id)
        .first()
    )
    if etiqueta is None:
        raise _nao_encontrado()
    return etiqueta


def atualizar_etiqueta(
    db: Session, *, filial_id: int, etiqueta_id: int, dados: dict
) -> dict:
    etiqueta = _buscar_etiqueta(db, filial_id, etiqueta_id)
    if "nome" in dados:
        etiqueta.nome = dados["nome"]
    if dados.get("cor"):
        etiqueta.cor = dados["cor"]
    db.commit()
    db.refresh(etiqueta)
    return _etiqueta_dict(etiqueta)


def excluir_etiqueta(db: Session, *, filial_id: int, etiqueta_id: int) -> None:
    """Apaga a etiqueta; os vínculos caem por `ON DELETE CASCADE` no banco."""
    etiqueta = _buscar_etiqueta(db, filial_id, etiqueta_id)
    db.delete(etiqueta)
    db.commit()


def _etiquetas_do_cartao(db: Session, cartao_id: int) -> list[dict]:
    linhas = (
        db.query(Etiqueta)
        .join(CartaoEtiqueta, CartaoEtiqueta.etiqueta_id == Etiqueta.id)
        .filter(CartaoEtiqueta.cartao_id == cartao_id)
        .order_by(Etiqueta.id.asc())
        .all()
    )
    return [_etiqueta_dict(e) for e in linhas]


def aplicar_etiqueta(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    etiqueta_id: int,
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    etiqueta = _buscar_etiqueta(db, filial_id, etiqueta_id)
    vinculo = (
        db.query(CartaoEtiqueta)
        .filter(
            CartaoEtiqueta.cartao_id == cartao.id,
            CartaoEtiqueta.etiqueta_id == etiqueta.id,
        )
        .first()
    )
    if vinculo is None:  # idempotente: aplicar duas vezes não duplica nem loga
        db.add(CartaoEtiqueta(cartao_id=cartao.id, etiqueta_id=etiqueta.id))
        _registrar_atividade(
            db,
            cartao.id,
            usuario.id,
            "etiqueta_add",
            {"etiqueta_id": etiqueta.id, "nome": etiqueta.nome, "cor": etiqueta.cor},
        )
        db.commit()
        db.refresh(cartao)
    return _para_cartao(db, cartao)


def remover_etiqueta(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    etiqueta_id: int,
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    apagados = (
        db.query(CartaoEtiqueta)
        .filter(
            CartaoEtiqueta.cartao_id == cartao.id,
            CartaoEtiqueta.etiqueta_id == etiqueta_id,
        )
        .delete(synchronize_session=False)
    )
    if apagados:
        _registrar_atividade(
            db, cartao.id, usuario.id, "etiqueta_remove", {"etiqueta_id": etiqueta_id}
        )
        db.commit()
        db.refresh(cartao)
    return _para_cartao(db, cartao)


# --------------------------------------------------------- Fase 2: checklists


def _posicoes_checklist(db: Session, cartao_id: int, exceto_id: int | None = None):
    q = db.query(CartaoChecklist.posicao).filter(CartaoChecklist.cartao_id == cartao_id)
    if exceto_id is not None:
        q = q.filter(CartaoChecklist.id != exceto_id)
    return [p for (p,) in q.order_by(CartaoChecklist.posicao.asc()).all()]


def _posicoes_item(db: Session, checklist_id: int, exceto_id: int | None = None):
    q = db.query(CartaoChecklistItem.posicao).filter(
        CartaoChecklistItem.checklist_id == checklist_id
    )
    if exceto_id is not None:
        q = q.filter(CartaoChecklistItem.id != exceto_id)
    return [p for (p,) in q.order_by(CartaoChecklistItem.posicao.asc()).all()]


def _rebalancear_checklists(db: Session, cartao_id: int) -> None:
    linhas = (
        db.query(CartaoChecklist)
        .filter(CartaoChecklist.cartao_id == cartao_id)
        .order_by(CartaoChecklist.posicao.asc())
        .all()
    )
    for indice, checklist in enumerate(linhas, start=1):
        checklist.posicao = PASSO_FRACIONARIO * indice
    db.flush()


def _rebalancear_itens(db: Session, checklist_id: int) -> None:
    linhas = (
        db.query(CartaoChecklistItem)
        .filter(CartaoChecklistItem.checklist_id == checklist_id)
        .order_by(CartaoChecklistItem.posicao.asc())
        .all()
    )
    for indice, item in enumerate(linhas, start=1):
        item.posicao = PASSO_FRACIONARIO * indice
    db.flush()


def _com_espaco(posicoes, indice: int, recarregar) -> Decimal:
    """Índice → fração; se o passo esgotou, rebalanceia e recalcula.

    `recarregar` deve rebalancear e devolver as posições já normalizadas.
    """
    try:
        return _posicao_para_indice(posicoes, indice)
    except _EspacoEsgotado:
        return _posicao_para_indice(recarregar(), indice)


def _progresso_checklists(db: Session, cartao_id: int) -> tuple[int, int]:
    """(total, concluídos) de itens de todos os checklists do cartão (RF11)."""
    base = (
        db.query(func.count(CartaoChecklistItem.id))
        .join(CartaoChecklist, CartaoChecklistItem.checklist_id == CartaoChecklist.id)
        .filter(CartaoChecklist.cartao_id == cartao_id)
    )
    total = base.scalar() or 0
    concluidos = base.filter(CartaoChecklistItem.concluido.is_(True)).scalar() or 0
    return total, concluidos


def _itens_do_checklist(db: Session, checklist_id: int) -> list[CartaoChecklistItem]:
    return (
        db.query(CartaoChecklistItem)
        .filter(CartaoChecklistItem.checklist_id == checklist_id)
        .order_by(CartaoChecklistItem.posicao.asc(), CartaoChecklistItem.id.asc())
        .all()
    )


def _item_dict(item: CartaoChecklistItem, nomes: dict[int, str]) -> dict:
    return {
        "id": item.id,
        "checklist_id": item.checklist_id,
        "texto": item.texto,
        "concluido": item.concluido,
        "responsavel_id": item.responsavel_id,
        "responsavel_nome": nomes.get(item.responsavel_id),
        "data_entrega": item.data_entrega,
        "posicao": item.posicao,
    }


def _checklist_dict(db: Session, checklist: CartaoChecklist) -> dict:
    itens = _itens_do_checklist(db, checklist.id)
    nomes = _nomes_usuarios(db, [i.responsavel_id for i in itens])
    return {
        "id": checklist.id,
        "cartao_id": checklist.cartao_id,
        "titulo": checklist.titulo,
        "posicao": checklist.posicao,
        "total": len(itens),
        "concluidos": sum(1 for i in itens if i.concluido),
        "itens": [_item_dict(i, nomes) for i in itens],
    }


def _buscar_checklist(
    db: Session, cartao_id: int, checklist_id: int
) -> CartaoChecklist:
    checklist = (
        db.query(CartaoChecklist)
        .filter(
            CartaoChecklist.id == checklist_id,
            CartaoChecklist.cartao_id == cartao_id,
        )
        .first()
    )
    if checklist is None:
        raise _nao_encontrado()
    return checklist


def _buscar_item(db: Session, checklist_id: int, item_id: int) -> CartaoChecklistItem:
    item = (
        db.query(CartaoChecklistItem)
        .filter(
            CartaoChecklistItem.id == item_id,
            CartaoChecklistItem.checklist_id == checklist_id,
        )
        .first()
    )
    if item is None:
        raise _nao_encontrado()
    return item


def listar_checklists(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int
) -> list[dict]:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    linhas = (
        db.query(CartaoChecklist)
        .filter(CartaoChecklist.cartao_id == cartao.id)
        .order_by(CartaoChecklist.posicao.asc(), CartaoChecklist.id.asc())
        .all()
    )
    return [_checklist_dict(db, c) for c in linhas]


def criar_checklist(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, dados: dict
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    posicoes = _posicoes_checklist(db, cartao.id)
    checklist = CartaoChecklist(
        cartao_id=cartao.id,
        titulo=dados["titulo"],
        posicao=_posicao_para_indice(posicoes, len(posicoes)),
    )
    db.add(checklist)
    db.flush()
    _registrar_atividade(
        db,
        cartao.id,
        usuario.id,
        "checklist_criado",
        {"checklist_id": checklist.id, "titulo": checklist.titulo},
    )
    db.commit()
    db.refresh(checklist)
    return _checklist_dict(db, checklist)


def atualizar_checklist(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    checklist_id: int,
    dados: dict,
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    checklist = _buscar_checklist(db, cartao.id, checklist_id)
    if dados.get("titulo") is not None:
        checklist.titulo = dados["titulo"]
    if dados.get("posicao") is not None:
        checklist.posicao = _com_espaco(
            _posicoes_checklist(db, cartao.id, exceto_id=checklist.id),
            dados["posicao"],
            lambda: (
                _rebalancear_checklists(db, cartao.id),
                _posicoes_checklist(db, cartao.id, exceto_id=checklist.id),
            )[1],
        )
    db.commit()
    db.refresh(checklist)
    return _checklist_dict(db, checklist)


def excluir_checklist(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, checklist_id: int
) -> None:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    checklist = _buscar_checklist(db, cartao.id, checklist_id)
    titulo = checklist.titulo
    db.delete(checklist)  # itens caem por cascade
    _registrar_atividade(
        db, cartao.id, usuario.id, "checklist_excluido", {"titulo": titulo}
    )
    db.commit()


def criar_item(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    checklist_id: int,
    dados: dict,
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    checklist = _buscar_checklist(db, cartao.id, checklist_id)
    responsavel_id = dados.get("responsavel_id")
    if responsavel_id is not None:
        _buscar_usuario_ativo(db, responsavel_id, filial_id)
    posicoes = _posicoes_item(db, checklist.id)
    item = CartaoChecklistItem(
        checklist_id=checklist.id,
        texto=dados["texto"],
        responsavel_id=responsavel_id,
        data_entrega=dados.get("data_entrega"),
        posicao=_posicao_para_indice(posicoes, len(posicoes)),
    )
    db.add(item)
    db.flush()
    _registrar_atividade(
        db,
        cartao.id,
        usuario.id,
        "item_criado",
        {"checklist_id": checklist.id, "item_id": item.id, "texto": item.texto},
    )
    db.commit()
    db.refresh(item)
    return _item_dict(item, _nomes_usuarios(db, [item.responsavel_id]))


def atualizar_item(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    checklist_id: int,
    item_id: int,
    dados: dict,
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    checklist = _buscar_checklist(db, cartao.id, checklist_id)
    item = _buscar_item(db, checklist.id, item_id)
    antes = {
        campo: getattr(item, campo)
        for campo in ("texto", "concluido", "responsavel_id", "data_entrega")
    }
    if dados.get("texto") is not None:
        item.texto = dados["texto"]
    if "responsavel_id" in dados:
        if dados["responsavel_id"] is not None:
            _buscar_usuario_ativo(db, dados["responsavel_id"], filial_id)
        item.responsavel_id = dados["responsavel_id"]
    if "data_entrega" in dados:
        item.data_entrega = dados["data_entrega"]
    if dados.get("concluido") is not None:
        item.concluido = bool(dados["concluido"])
    if dados.get("posicao") is not None:
        item.posicao = _com_espaco(
            _posicoes_item(db, checklist.id, exceto_id=item.id),
            dados["posicao"],
            lambda: (
                _rebalancear_itens(db, checklist.id),
                _posicoes_item(db, checklist.id, exceto_id=item.id),
            )[1],
        )
    db.flush()
    evento: dict = {"checklist_id": checklist.id, "item_id": item.id}
    virou = dados.get("concluido")
    antes_concluido = antes["concluido"]
    if virou is not None and bool(virou) != antes_concluido:
        if item.concluido:
            _registrar_atividade(db, cartao.id, usuario.id, "item_concluido", evento)
        else:
            _registrar_atividade(db, cartao.id, usuario.id, "item_reaberto", evento)
    elif any(getattr(item, campo) != antes[campo] for campo in antes):
        _registrar_atividade(db, cartao.id, usuario.id, "item_atualizado", evento)
    db.commit()
    db.refresh(item)
    return _item_dict(item, _nomes_usuarios(db, [item.responsavel_id]))


def excluir_item(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    checklist_id: int,
    item_id: int,
) -> None:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    checklist = _buscar_checklist(db, cartao.id, checklist_id)
    item = _buscar_item(db, checklist.id, item_id)
    texto = item.texto
    db.delete(item)
    _registrar_atividade(
        db,
        cartao.id,
        usuario.id,
        "item_excluido",
        {"checklist_id": checklist.id, "item_id": item_id, "texto": texto},
    )
    db.commit()


# -------------------------------------------------------- Fase 2: comentários


def _comentarios_contados(db: Session, cartao_id: int) -> int:
    return (
        db.query(func.count(CartaoComentario.id))
        .filter(
            CartaoComentario.cartao_id == cartao_id,
            CartaoComentario.excluido.is_(False),
        )
        .scalar()
        or 0
    )


def _comentario_dict(comentario: CartaoComentario, nomes: dict[int, str]) -> dict:
    return {
        "id": comentario.id,
        "cartao_id": comentario.cartao_id,
        "usuario_id": comentario.usuario_id,
        "usuario_nome": nomes.get(comentario.usuario_id),
        # Soft-delete: a linha permanece (respostas não quebram), o texto não.
        "texto": None if comentario.excluido else comentario.texto,
        "resposta_a_id": comentario.resposta_a_id,
        "excluido": comentario.excluido,
        "criado_em": comentario.criado_em,
        "editado_em": comentario.editado_em,
    }


def _comentario_do_cartao(
    db: Session, cartao_id: int, comentario_id: int
) -> CartaoComentario:
    comentario = (
        db.query(CartaoComentario)
        .filter(
            CartaoComentario.id == comentario_id,
            CartaoComentario.cartao_id == cartao_id,
        )
        .first()
    )
    if comentario is None:
        raise _nao_encontrado()
    return comentario


def listar_comentarios(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int
) -> list[dict]:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    linhas = (
        db.query(CartaoComentario)
        .filter(CartaoComentario.cartao_id == cartao.id)
        .order_by(CartaoComentario.criado_em.asc(), CartaoComentario.id.asc())
        .all()
    )
    nomes = _nomes_usuarios(db, [c.usuario_id for c in linhas])
    return [_comentario_dict(c, nomes) for c in linhas]


def criar_comentario(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, dados: dict
) -> dict:
    """Comentário com resposta em **um** nível (RF14)."""
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    resposta_a = dados.get("resposta_a_id")
    if resposta_a is not None:
        pai = _comentario_do_cartao(db, cartao.id, resposta_a)
        if pai.resposta_a_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Só é possível responder em um nível.",
            )
    comentario = CartaoComentario(
        cartao_id=cartao.id,
        usuario_id=usuario.id,
        texto=dados["texto"],
        resposta_a_id=resposta_a,
    )
    db.add(comentario)
    db.flush()
    _registrar_atividade(
        db, cartao.id, usuario.id, "comentario", {"comentario_id": comentario.id}
    )
    db.commit()
    db.refresh(comentario)
    return _comentario_dict(comentario, _nomes_usuarios(db, [comentario.usuario_id]))


def atualizar_comentario(
    db: Session,
    *,
    usuario: Usuario,
    filial_id: int,
    cartao_id: int,
    comentario_id: int,
    dados: dict,
) -> dict:
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    comentario = _comentario_do_cartao(db, cartao.id, comentario_id)
    if comentario.excluido:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comentário excluído não pode ser editado.",
        )
    if comentario.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o autor pode editar o comentário.",
        )
    comentario.texto = dados["texto"]
    comentario.editado_em = datetime.now(UTC)
    db.commit()
    db.refresh(comentario)
    return _comentario_dict(comentario, _nomes_usuarios(db, [comentario.usuario_id]))


def excluir_comentario(
    db: Session, *, usuario: Usuario, filial_id: int, cartao_id: int, comentario_id: int
) -> dict:
    """Soft-delete (RF14): a linha fica para não quebrar as respostas.

    O autor exclui o próprio comentário; gestores (Admin/Gerente) moderam.
    """
    cartao = _buscar_cartao(db, usuario, cartao_id, filial_id)
    comentario = _comentario_do_cartao(db, cartao.id, comentario_id)
    if comentario.usuario_id != usuario.id and not _e_gestor(usuario):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o autor ou um gestor pode excluir o comentário.",
        )
    if not comentario.excluido:
        comentario.excluido = True
        _registrar_atividade(
            db,
            cartao.id,
            usuario.id,
            "comentario_excluido",
            {"comentario_id": comentario.id},
        )
        db.commit()
        db.refresh(comentario)
    return _comentario_dict(comentario, _nomes_usuarios(db, [comentario.usuario_id]))
