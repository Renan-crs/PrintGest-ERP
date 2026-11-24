"""Simulação de preço de variações — guia `fluxo_variacoes_produtos_servicos.md` (V0).

Aqui as regras vêm no corpo da requisição: o objetivo é validar o motor puro e
oferecer ao balcão/orçamento um "simulador sem salvar" (RF-VR-07/09/10/14),
disponível inclusive em modo leitura da licença. A persistência de
`tabela_preco`/`regra_preco` virá na etapa seguinte.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.deps import UsuarioDep
from app.schemas import ItemResponse
from app.services.precificacao_variacao import (
    MODO_TODA_A_QUANTIDADE,
    TIPO_ACRESCIMO_FIXO,
    TIPO_ACRESCIMO_UNITARIO,
    TIPO_MULTIPLICADOR,
    FaixaInvalidaError,
    FaixaPreco,
    Modificador,
    PrecoNaoCadastradoError,
    RegraPreco,
    calcular_linha,
)


class FaixaIn(BaseModel):
    qtd_min: int = Field(ge=1)
    qtd_max: int | None = Field(default=None, ge=1)
    preco_unitario: Decimal = Field(ge=0)


class ModificadorIn(BaseModel):
    tipo: Literal["MULTIPLICADOR", "ACRESCIMO_UNITARIO", "ACRESCIMO_FIXO"]
    valor: Decimal
    descricao: str | None = None


class SimularPrecoIn(BaseModel):
    preco_base: Decimal = Field(default=Decimal("0"), ge=0)
    quantidade: int = Field(ge=1, le=1_000_000)
    faixas: list[FaixaIn] = Field(default_factory=list)
    modificadores: list[ModificadorIn] = Field(default_factory=list)
    minimo: Decimal | None = Field(default=None, ge=0)
    modo_faixa: Literal["TODA_A_QUANTIDADE", "PROGRESSIVA"] = MODO_TODA_A_QUANTIDADE


class SimularPrecoOut(BaseModel):
    quantidade: int
    preco_unitario: Decimal
    valor_itens: Decimal
    acrescimos_fixos: Decimal
    minimo_aplicado: Decimal
    total: Decimal
    faixa: str | None
    explicacao: list[str]


router = APIRouter(prefix="/variacoes", tags=["variações"])


@router.post("/preco/simular")
def simular_preco(
    body: SimularPrecoIn, _usuario: UsuarioDep
) -> ItemResponse[SimularPrecoOut]:
    """Calcula o preço da linha sem gravar nada (não é escrita no modo leitura)."""
    regra = RegraPreco(
        preco_base=body.preco_base,
        faixas=tuple(
            FaixaPreco(f.qtd_min, f.qtd_max, f.preco_unitario) for f in body.faixas
        ),
        modificadores=tuple(
            Modificador(m.tipo, m.valor, m.descricao or "") for m in body.modificadores
        ),
        minimo=body.minimo,
        modo_faixa=body.modo_faixa,
    )
    try:
        linha = calcular_linha(regra, body.quantidade)
    except PrecoNaoCadastradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"codigo": "PRECO_NAO_CADASTRADO", "mensagem": str(exc)},
        ) from exc
    except (FaixaInvalidaError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ItemResponse(
        data=SimularPrecoOut(
            quantidade=linha.quantidade,
            preco_unitario=linha.preco_unitario,
            valor_itens=linha.valor_itens,
            acrescimos_fixos=linha.acrescimos_fixos,
            minimo_aplicado=linha.minimo_aplicado,
            total=linha.total,
            faixa=linha.faixa.rotulo() if linha.faixa else None,
            explicacao=list(linha.explicacao),
        )
    )


def registrar(api: APIRouter) -> None:
    api.include_router(router)
