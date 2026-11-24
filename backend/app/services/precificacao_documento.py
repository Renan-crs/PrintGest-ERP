"""Integração do motor de preço com venda/OS — sem migration (guia V0).

Quando o item traz `regra_preco`, o **servidor** calcula o unitário e o total
com `calcular_linha` e devolve a explicação. Sem regra, o comportamento legado
(`valor_unitario` enviado pelo cliente) é preservado — é o que mantém
compatibilidade com o PDV atual e com os itens de fornecedor, cujo preço
pertence a `cotacao_service`.

A explicação é um atributo transiente (`_explicacao`) na instância do item:
não vira coluna, não entra em `INSERT`/`UPDATE` e é devolvida somente na
resposta da requisição que calculou. Em consultas posteriores volta vazia
(enquanto a regra não for persistida na Fase V1).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException, status

from app.schemas.precificacao import RegraPrecoIn
from app.services.precificacao_variacao import (
    FaixaInvalidaError,
    FaixaPreco,
    Modificador,
    PrecoNaoCadastradoError,
    RegraPreco,
    calcular_linha,
)

_TWO = Decimal("0.01")
_ZERO = Decimal("0.00")


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(_TWO, rounding=ROUND_HALF_UP)


def resolver_preco_linha(
    *,
    valor_unitario: Decimal,
    quantidade: Decimal,
    desconto: Decimal,
    regra: RegraPrecoIn | None,
) -> tuple[Decimal, Decimal, list[str]]:
    """Devolve `(unitário a gravar, total da linha, explicação)`."""
    if regra is None:
        total = _centavos(valor_unitario * quantidade - desconto)
        return valor_unitario, max(total, _ZERO), []

    # O motor trabalha com contagem inteira de unidades. Nunca converter com
    # `int()` em silêncio: isso mudaria a faixa e a quantidade baixada do estoque.
    if quantidade != quantidade.to_integral_value():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Regras de preço por faixa exigem quantidade inteira.",
        )

    regra_interna = RegraPreco(
        preco_base=regra.preco_base,
        faixas=tuple(
            FaixaPreco(f.qtd_min, f.qtd_max, f.preco_unitario) for f in regra.faixas
        ),
        modificadores=tuple(
            Modificador(m.tipo, m.valor, m.descricao or "") for m in regra.modificadores
        ),
        minimo=regra.minimo,
        modo_faixa=regra.modo_faixa,
    )
    try:
        linha = calcular_linha(regra_interna, int(quantidade))
    except PrecoNaoCadastradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "PRECO_NAO_CADASTRADO", "mensagem": str(exc)},
        ) from exc
    except (FaixaInvalidaError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # O total vem do motor (inclui acréscimo fixo e mínimo); o unitário é
    # arredondado para a coluna Numeric(14,2). Não recomputar a partir dele.
    total = _centavos(linha.total - desconto)
    return _centavos(linha.preco_unitario), max(total, _ZERO), list(linha.explicacao)
