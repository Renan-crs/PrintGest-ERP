"""Motor de preço determinístico para variações — guia `fluxo_variacoes_produtos_servicos.md` (V0/V1).

Função **pura**: não toca banco, não depende de request e produz o mesmo
resultado no balcão, no orçamento e na OS. É a base do RF-VR-07/09/10/11 e do
primeiro critério de pronto do Anexo B do guia.

Regras implementadas (seção 7 do guia):
- faixa de quantidade nos modos `TODA_A_QUANTIDADE` (padrão) e `PROGRESSIVA`;
- modificadores na ordem: multiplicadores → acréscimos por unidade →
  acréscimos fixos → mínimo da linha;
- unitário guardado com 4 casas, total da linha com `ROUND_HALF_UP` em 2 casas;
- `PRECO_NAO_CADASTRADO` quando não há regra — **nunca preço zero em silêncio**;
- explicação da linha (RF-VR-14) com a origem de cada valor.

A persistência de `tabela_preco`/`regra_preco` (RF-VR-08/12) e o snapshot no
documento (RF-VR-21) são etapas seguintes — aqui as regras são passadas como
dados, o que mantém o cálculo testável pela tabela de casos da seção 16.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

_CENTAVOS = Decimal("0.01")
_QUATRO_CASAS = Decimal("0.0001")

MODO_TODA_A_QUANTIDADE = "TODA_A_QUANTIDADE"
MODO_PROGRESSIVA = "PROGRESSIVA"
_MODOS = (MODO_TODA_A_QUANTIDADE, MODO_PROGRESSIVA)

TIPO_MULTIPLICADOR = "MULTIPLICADOR"
TIPO_ACRESCIMO_UNITARIO = "ACRESCIMO_UNITARIO"
TIPO_ACRESCIMO_FIXO = "ACRESCIMO_FIXO"
_TIPOS = (TIPO_MULTIPLICADOR, TIPO_ACRESCIMO_UNITARIO, TIPO_ACRESCIMO_FIXO)


class PrecoNaoCadastradoError(ValueError):
    """Sem regra vigente para a combinação (código `PRECO_NAO_CADASTRADO`)."""


class FaixaInvalidaError(ValueError):
    """Faixas sobrepostas, com buraco ou fora da ordem (regra de integridade 3)."""


def _decimal(valor) -> Decimal:
    """Aceita `Decimal`, int, str ou float sem herdar o binário do float."""
    return Decimal(str(valor))


def _centavos(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _quatro_casas(valor: Decimal) -> Decimal:
    return valor.quantize(_QUATRO_CASAS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FaixaPreco:
    qtd_min: int
    qtd_max: int | None
    preco_unitario: Decimal

    def contem(self, quantidade: int) -> bool:
        return self.qtd_min <= quantidade and (
            self.qtd_max is None or quantidade <= self.qtd_max
        )

    def rotulo(self) -> str:
        return f"{self.qtd_min}-{self.qtd_max or '…'}"


@dataclass(frozen=True)
class Modificador:
    tipo: str
    valor: Decimal
    descricao: str = ""


@dataclass(frozen=True)
class RegraPreco:
    preco_base: Decimal
    faixas: tuple[FaixaPreco, ...] = ()
    modificadores: tuple[Modificador, ...] = ()
    minimo: Decimal | None = None
    modo_faixa: str = MODO_TODA_A_QUANTIDADE


@dataclass(frozen=True)
class LinhaCalculada:
    quantidade: int
    preco_unitario: Decimal
    valor_itens: Decimal
    acrescimos_fixos: Decimal
    minimo_aplicado: Decimal
    total: Decimal
    faixa: FaixaPreco | None
    explicacao: tuple[str, ...]


def validar_faixas(faixas: Sequence[FaixaPreco]) -> None:
    """Faixas devem começar em 1, ser contínuas e não se sobrepor."""
    if not faixas:
        return
    ordenadas = sorted(faixas, key=lambda f: f.qtd_min)
    if ordenadas[0].qtd_min != 1:
        raise FaixaInvalidaError("A primeira faixa deve começar em 1.")
    for indice, faixa in enumerate(ordenadas):
        if faixa.qtd_min < 1:
            raise FaixaInvalidaError("As quantidades mínimas devem ser >= 1.")
        if faixa.qtd_max is not None and faixa.qtd_max < faixa.qtd_min:
            raise FaixaInvalidaError("qtd_max não pode ser menor que qtd_min.")
        if faixa.preco_unitario < 0:
            raise FaixaInvalidaError("Preço de faixa não pode ser negativo.")
        if indice + 1 < len(ordenadas):
            proxima = ordenadas[indice + 1]
            if faixa.qtd_max is None or proxima.qtd_min != faixa.qtd_max + 1:
                raise FaixaInvalidaError(
                    f"Faixas descontínuas ou sobrepostas: {faixa.rotulo()} → "
                    f"{proxima.rotulo()}."
                )


def selecionar_faixa(
    faixas: Sequence[FaixaPreco], quantidade: int
) -> FaixaPreco | None:
    for faixa in faixas:
        if faixa.contem(quantidade):
            return faixa
    return None


def _unitario_das_faixas(
    faixas: Sequence[FaixaPreco], quantidade: int, modo: str
) -> Decimal:
    total = Decimal(0)
    if modo == MODO_TODA_A_QUANTIDADE:
        faixa = selecionar_faixa(faixas, quantidade)
        if faixa is None:
            raise PrecoNaoCadastradoError(
                f"Não há faixa de preço para a quantidade {quantidade}."
            )
        return faixa.preco_unitario

    restante = quantidade
    for faixa in sorted(faixas, key=lambda f: f.qtd_min):
        if restante <= 0:
            break
        largura = (
            faixa.qtd_max - faixa.qtd_min + 1
            if faixa.qtd_max is not None
            else restante
        )
        quantidade_na_faixa = min(restante, largura)
        total += faixa.preco_unitario * quantidade_na_faixa
        restante -= quantidade_na_faixa
    if restante > 0:
        raise PrecoNaoCadastradoError(
            f"Não há faixa de preço para a quantidade {quantidade}."
        )
    return total / Decimal(quantidade)


def calcular_linha(regra: RegraPreco, quantidade: int) -> LinhaCalculada:
    """Executa as 11 etapas do cálculo (guia §7.1)."""
    if quantidade < 1:
        raise ValueError("A quantidade deve ser pelo menos 1.")

    if regra.modo_faixa not in _MODOS:
        raise ValueError(f"Modo de faixa inválido: {regra.modo_faixa}.")

    explicacao: list[str] = []
    faixa: FaixaPreco | None = None

    if regra.faixas:
        validar_faixas(regra.faixas)
        faixa = selecionar_faixa(regra.faixas, quantidade)
        unitario = _unitario_das_faixas(regra.faixas, quantidade, regra.modo_faixa)
        if regra.modo_faixa == MODO_PROGRESSIVA:
            explicacao.append(
                f"Faixas progressivas ({', '.join(f.rotulo() for f in regra.faixas)})"
            )
        elif faixa is not None:
            explicacao.append(
                f"Faixa {faixa.rotulo()}: {faixa.preco_unitario} por unidade"
            )
    else:
        unitario = _decimal(regra.preco_base)
        explicacao.append(f"Preço base: {unitario} por unidade")

    if unitario <= 0:
        raise PrecoNaoCadastradoError(
            "Esta combinação não tem preço cadastrado. "
            "Peça ao gerente para cadastrar ou use preço manual."
        )

    for mod in regra.modificadores:
        if mod.tipo not in _TIPOS:
            raise ValueError(f"Tipo de modificador inválido: {mod.tipo}.")
        valor = _decimal(mod.valor)
        rotulo = mod.descricao or mod.tipo.replace("_", " ").title()
        if mod.tipo == TIPO_MULTIPLICADOR:
            if valor <= 0:
                raise ValueError("Multiplicador deve ser maior que zero.")
            unitario *= valor
            explicacao.append(f"{rotulo}: ×{valor}")
        elif mod.tipo == TIPO_ACRESCIMO_UNITARIO:
            unitario += valor
            explicacao.append(f"{rotulo}: +{valor} por unidade")

    unitario = _quatro_casas(unitario)
    valor_itens = _centavos(unitario * quantidade)

    acrescimos_fixos = sum(
        (_decimal(m.valor) for m in regra.modificadores if m.tipo == TIPO_ACRESCIMO_FIXO),
        Decimal(0),
    )
    for mod in regra.modificadores:
        if mod.tipo == TIPO_ACRESCIMO_FIXO:
            explicacao.append(
                f"{mod.descricao or 'Acréscimo fixo'}: +{_decimal(mod.valor)}"
            )

    total = _centavos(valor_itens + acrescimos_fixos)

    minimo_aplicado = Decimal("0.00")
    if regra.minimo is not None and total < _decimal(regra.minimo):
        total = _centavos(_decimal(regra.minimo))
        minimo_aplicado = _centavos(total - valor_itens - acrescimos_fixos)
        explicacao.append(f"Mínimo por linha: {total}")

    return LinhaCalculada(
        quantidade=quantidade,
        preco_unitario=unitario,
        valor_itens=valor_itens,
        acrescimos_fixos=_centavos(acrescimos_fixos),
        minimo_aplicado=minimo_aplicado,
        total=total,
        faixa=faixa,
        explicacao=tuple(explicacao),
    )


def selecionar_regra(
    candidatos: Sequence[tuple[str, RegraPreco | None]],
) -> tuple[str, RegraPreco]:
    """Precedência RF-VR-08: a primeira regra não nula da lista (cliente → filial → padrão)."""
    for origem, regra in candidatos:
        if regra is not None:
            return origem, regra
    raise PrecoNaoCadastradoError(
        "Esta combinação não tem preço cadastrado. "
        "Peça ao gerente para cadastrar ou use preço manual."
    )


def ratear_desconto(
    totais: Sequence[Decimal], desconto: Decimal
) -> list[Decimal]:
    """Rateia o desconto proporcionalmente; a última linha absorve o resíduo (guia §7.5)."""
    if not totais:
        raise ValueError("É preciso ao menos uma linha para ratear o desconto.")
    desconto = _decimal(desconto)
    if desconto < 0:
        raise ValueError("Desconto não pode ser negativo.")
    soma = sum((_decimal(t) for t in totais), Decimal(0))
    if desconto > soma:
        raise ValueError("O desconto não pode ser maior que o total das linhas.")
    if soma == 0:
        return [_centavos(Decimal(0)) for _ in totais]
    rateios = [
        _centavos(_decimal(t) * desconto / soma) for t in totais
    ]
    residuo = desconto - sum(rateios, Decimal(0))
    rateios[-1] = _centavos(rateios[-1] + residuo)
    return rateios
