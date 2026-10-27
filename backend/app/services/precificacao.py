"""Motor de precificação — núcleo de cálculo do M1 (PRD v3.0 §3.1/§3.2.1).

A regra de negócio central do orçamento com fornecedor (decidida em 26/10/2026,
Q-01):

- **CP** (custo de produção) = `VF × (1 + acrescimo_fornecedor_pct/100)`
  — padrão 130% → `VF × 2,30`;
- **VO** (valor do orçamento) = `CP × (1 + markup_orcamento_pct/100)`
  — padrão 6% → `CP × 1,06`. É markup sobre a base, **não** margem sobre o
  preço final (`CP ÷ 0,94` foi descartado na decisão Q-01).

Arredondamento: `ROUND_HALF_UP` explícito (o padrão *banker's* do `Decimal`
daria 200,90 no caso canônico VF 87,35), **CP arredondado antes do VO** — a
fórmula normativa é a sequencial; o atalho `VF × 2,438` é aproximação e diverge
em borda (VF 0,05 → sequencial 0,13, direto 0,12).

Cada item terceirizado grava um **snapshot** (VF, percentuais aplicados, CP e
VO): mudar o parâmetro global não altera orçamentos existentes (PRD §3.2.1).
A sobrescrita por fornecedor/serviço é do M2 (decisão Q-04) — aqui os
parâmetros são globais por filial.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.models.config import PrecoParametro

_CENTAVOS = Decimal("0.01")

# Parâmetros globais por filial (Configurações > Precificação, Admin).
PARAMETROS_PADRAO: dict[str, Decimal] = {
    "acrescimo_fornecedor_pct": Decimal("130"),
    "markup_orcamento_pct": Decimal("6"),
}

_LIMITE_PCT = Decimal("100000")


# ------------------------------------------------------------- cálculo puro


def _fator(pct: Decimal) -> Decimal:
    return Decimal("1") + pct / Decimal("100")


def _pct_valido(valor, nome: str) -> Decimal:
    pct = Decimal(str(valor))
    if pct < 0 or pct > _LIMITE_PCT:
        raise ValueError(f"{nome} deve estar entre 0 e {_LIMITE_PCT}.")
    return pct


def _vf_valido(valor, nome: str = "VF") -> Decimal:
    vf = Decimal(str(valor))
    if vf < 0:
        raise ValueError(f"{nome} não pode ser negativo.")
    return vf


def calcular_cp(vf, acrescimo_fornecedor_pct) -> Decimal:
    """CP = VF × (1 + acréscimo%) — arredondado meio para cima, 2 casas."""
    return (
        _vf_valido(vf) * _fator(_pct_valido(acrescimo_fornecedor_pct, "acréscimo"))
    ).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_vo(cp, markup_orcamento_pct) -> Decimal:
    """VO = CP × (1 + markup%) sobre o **CP já arredondado** (fórmula normativa)."""
    return (
        _vf_valido(cp, "CP") * _fator(_pct_valido(markup_orcamento_pct, "markup"))
    ).quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _pct_texto(pct: Decimal) -> str:
    """Percentual como texto limpo: 100.000 → '100'; 33.500 → '33.5'."""
    texto = str(pct)
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto or "0"


def snapshot_item_terceirizado(
    vf, acrescimo_fornecedor_pct, markup_orcamento_pct
) -> dict:
    """Snapshot do item terceirizado (PRD §3.2.1): valores em texto, prontos
    para `ordem_servico_item` — o que foi aplicado fica registrado para sempre."""
    vf_dec = _vf_valido(vf)
    acrescimo = _pct_valido(acrescimo_fornecedor_pct, "acréscimo")
    markup = _pct_valido(markup_orcamento_pct, "markup")
    cp = calcular_cp(vf_dec, acrescimo)
    vo = calcular_vo(cp, markup)
    return {
        "vf": f"{vf_dec:.2f}",
        "acrescimo_fornecedor_pct": _pct_texto(acrescimo),
        "markup_orcamento_pct": _pct_texto(markup),
        "cp": f"{cp:.2f}",
        "vo": f"{vo:.2f}",
    }


# ------------------------------------------------- parâmetros (por filial)


def parametros(
    db: Session, *, filial_id: int, fornecedor_id: int | None = None
) -> dict[str, Decimal]:
    """Parâmetros vigentes: default ← global ← sobrescrita do fornecedor.

    Quando `fornecedor_id` é informado, linhas com aquele fornecedor
    **sobrescrevem** as globais (precedência M2, Q-04). Sem o parâmetro,
    devolve só as globais (comportamento M1 preservado).
    """
    valores = dict(PARAMETROS_PADRAO)
    linhas = (
        db.query(PrecoParametro)
        .filter(PrecoParametro.filial_id == filial_id)
        .filter(
            PrecoParametro.fornecedor_id.is_(None)
            if fornecedor_id is None
            else (
                (PrecoParametro.fornecedor_id.is_(None))
                | (PrecoParametro.fornecedor_id == fornecedor_id)
            )
        )
        .all()
    )
    # aplica na ordem: global primeiro, sobrescrita depois
    for linha in sorted(linhas, key=lambda l: l.fornecedor_id is not None):
        if linha.chave in valores:
            valores[linha.chave] = Decimal(linha.valor)
    return valores


def definir_parametros(
    db: Session,
    *,
    filial_id: int,
    usuario_id: int,
    dados: dict,
    fornecedor_id: int | None = None,
) -> dict[str, Decimal]:
    """Upsert dos parâmetros informados; devolve os vigentes depois da mudança.

    Sem `fornecedor_id`: altera os globais da filial (M1). Com: altera a
    **sobrescrita** daquele fornecedor (M2, Q-04) — o global fica intacto.
    Registra quem alterou e quando (NFR de rastreabilidade do PRD v3.0).
    """
    atuais = parametros(db, filial_id=filial_id, fornecedor_id=fornecedor_id)
    recebidos = {}
    for chave in PARAMETROS_PADRAO:
        if chave in dados and dados[chave] is not None:
            pct = _pct_valido(dados[chave], chave)
            if pct == atuais[chave]:
                continue
            recebidos[chave] = pct
    for chave, pct in recebidos.items():
        linha = (
            db.query(PrecoParametro)
            .filter(
                PrecoParametro.filial_id == filial_id,
                PrecoParametro.chave == chave,
                PrecoParametro.fornecedor_id == fornecedor_id,
            )
            .first()
        )
        if linha is None:
            linha = PrecoParametro(
                filial_id=filial_id, chave=chave, fornecedor_id=fornecedor_id
            )
            db.add(linha)
        linha.valor = pct
        linha.usuario_id = usuario_id
        db.flush()
    db.commit()
    return parametros(db, filial_id=filial_id, fornecedor_id=fornecedor_id)


def calcular_item_terceirizado(
    db: Session, *, filial_id: int, vf, fornecedor_id: int | None = None
) -> dict:
    """Conveniência para o fluxo do M1/M2: lê os parâmetros (com sobrescrita
    do fornecedor, quando informado) e devolve o snapshot do item."""
    pcts = parametros(db, filial_id=filial_id, fornecedor_id=fornecedor_id)
    return snapshot_item_terceirizado(
        vf,
        pcts["acrescimo_fornecedor_pct"],
        pcts["markup_orcamento_pct"],
    )
