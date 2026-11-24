"""Tabela de casos do guia de variações (seção 16) — motor de preço puro V0/V1."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.precificacao_variacao import (
    MODO_PROGRESSIVA,
    TIPO_ACRESCIMO_FIXO,
    TIPO_ACRESCIMO_UNITARIO,
    TIPO_MULTIPLICADOR,
    FaixaInvalidaError,
    FaixaPreco,
    Modificador,
    PrecoNaoCadastradoError,
    RegraPreco,
    calcular_linha,
    ratear_desconto,
    selecionar_regra,
    validar_faixas,
)


def D(valor: str) -> Decimal:
    return Decimal(valor)


def _faixas_sulfite() -> tuple[FaixaPreco, ...]:
    return (
        FaixaPreco(1, 49, D("1.00")),
        FaixaPreco(50, 199, D("0.80")),
        FaixaPreco(200, None, D("0.60")),
    )


# ------------------------------------------------------------- T-VR-03


@pytest.mark.parametrize(
    "quantidade,unitario,total",
    [
        (49, "1.0000", "49.00"),
        (50, "0.8000", "40.00"),
        (199, "0.8000", "159.20"),
        (200, "0.6000", "120.00"),
    ],
)
def test_T_VR_03_bordas_das_faixas(quantidade, unitario, total):
    linha = calcular_linha(RegraPreco(D("0"), faixas=_faixas_sulfite()), quantidade)
    assert linha.preco_unitario == D(unitario)
    assert linha.total == D(total)


# ------------------------------------------------------------- T-VR-04


def test_T_VR_04_faixa_vale_para_toda_a_quantidade():
    linha = calcular_linha(RegraPreco(D("0"), faixas=_faixas_sulfite()), 120)
    assert linha.total == D("96.00")


def test_T_VR_04_faixa_progressiva():
    regra = RegraPreco(
        D("0"), faixas=_faixas_sulfite(), modo_faixa=MODO_PROGRESSIVA
    )
    linha = calcular_linha(regra, 120)
    # 49 × 1,00 + 71 × 0,80 = 105,80
    assert linha.total == D("105.80")


# ------------------------------------------------------------- T-VR-05


def test_T_VR_05_modificadores_na_ordem_correta():
    regra = RegraPreco(
        D("0"),
        faixas=_faixas_sulfite(),
        modificadores=(
            Modificador(TIPO_MULTIPLICADOR, D("1.6"), "Frente e verso"),
            Modificador(TIPO_ACRESCIMO_UNITARIO, D("0.10"), "Corte"),
        ),
    )
    linha = calcular_linha(regra, 100)
    # 0,80 × 1,6 = 1,28; + 0,10 = 1,38; 100 × 1,38 = 138,00
    assert linha.preco_unitario == D("1.3800")
    assert linha.valor_itens == D("138.00")
    assert linha.total == D("138.00")
    assert "Frente e verso: ×1.6" in linha.explicacao
    assert "Corte: +0.10 por unidade" in linha.explicacao


def test_acrescimo_fixo_e_minimo_aplicado_depois_dos_unitarios():
    regra = RegraPreco(
        D("10"),
        modificadores=(
            Modificador(TIPO_MULTIPLICADOR, D("2"), "Dobro"),
            Modificador(TIPO_ACRESCIMO_UNITARIO, D("5"), "Acabamento"),
            Modificador(TIPO_ACRESCIMO_FIXO, D("30"), "Taxa de arte"),
        ),
        minimo=D("100"),
    )
    linha = calcular_linha(regra, 2)
    # (10 × 2 + 5) × 2 = 50; + 30 = 80; mínimo 100
    assert linha.preco_unitario == D("25.0000")
    assert linha.valor_itens == D("50.00")
    assert linha.acrescimos_fixos == D("30.00")
    assert linha.minimo_aplicado == D("20.00")
    assert linha.total == D("100.00")


# ------------------------------------------------------------- T-VR-06


def test_T_VR_06_minimo_por_linha():
    regra = RegraPreco(D("1.00"), minimo=D("5.00"))
    linha = calcular_linha(regra, 1)
    assert linha.preco_unitario == D("1.0000")
    assert linha.total == D("5.00")
    assert linha.minimo_aplicado == D("4.00")


# ------------------------------------------------------------- T-VR-07


def test_T_VR_07_arredondamento_quatro_casas_no_unitario():
    linha = calcular_linha(RegraPreco(D("0.3333")), 300)
    assert linha.preco_unitario == D("0.3333")
    assert linha.total == D("99.99")


def test_T_VR_07_rateio_de_desconto_residuo_na_ultima_linha():
    assert ratear_desconto([D("100"), D("200"), D("300")], D("10")) == [
        D("1.67"),
        D("3.33"),
        D("5.00"),
    ]
    assert ratear_desconto([D("1"), D("1"), D("1")], D("0.01")) == [
        D("0.00"),
        D("0.00"),
        D("0.01"),
    ]


def test_rateio_rejeita_desconto_maior_que_total():
    with pytest.raises(ValueError):
        ratear_desconto([D("1")], D("2"))


# ------------------------------------------------------------- T-VR-02 / 08


def test_T_VR_02_sem_preco_nunca_zero_em_silencio():
    with pytest.raises(PrecoNaoCadastradoError):
        calcular_linha(RegraPreco(D("0")), 10)


def test_T_VR_02_quantidade_fora_das_faixas():
    faixas_fechadas = (FaixaPreco(1, 49, D("1.00")), FaixaPreco(50, 199, D("0.80")))
    with pytest.raises(PrecoNaoCadastradoError):
        calcular_linha(RegraPreco(D("0"), faixas=faixas_fechadas), 300)


def test_T_VR_08_precedencia_cliente_filial_padrao():
    padrao = RegraPreco(D("1.00"))
    filial = RegraPreco(D("2.00"))
    origem, regra = selecionar_regra(
        [("cliente", None), ("filial", filial), ("padrao", padrao)]
    )
    assert origem == "filial"
    assert regra is filial

    origem, regra = selecionar_regra(
        [("cliente", None), ("filial", None), ("padrao", padrao)]
    )
    assert origem == "padrao"

    with pytest.raises(PrecoNaoCadastradoError):
        selecionar_regra([("cliente", None), ("filial", None), ("padrao", None)])


# ------------------------------------------------------------- integridade


@pytest.mark.parametrize(
    "faixas",
    [
        (FaixaPreco(2, 49, D("1")),),  # não começa em 1
        (FaixaPreco(1, 20, D("1")), FaixaPreco(30, 49, D("1"))),  # buraco
        (FaixaPreco(1, 50, D("1")), FaixaPreco(40, 99, D("1"))),  # sobreposição
        (FaixaPreco(1, None, D("1")), FaixaPreco(50, 99, D("1"))),  # aberta antes
    ],
)
def test_faixas_descontinuas_sao_rejeitadas(faixas):
    with pytest.raises(FaixaInvalidaError):
        validar_faixas(faixas)


def test_quantidade_invalida():
    with pytest.raises(ValueError):
        calcular_linha(RegraPreco(D("1")), 0)


def test_explicacao_traz_todas_as_etapas():
    regra = RegraPreco(
        D("0"),
        faixas=_faixas_sulfite(),
        modificadores=(
            Modificador(TIPO_MULTIPLICADOR, D("1.6"), "Frente e verso"),
            Modificador(TIPO_ACRESCIMO_FIXO, D("30"), "Taxa de arte"),
        ),
        minimo=D("200"),
    )
    texto = " | ".join(calcular_linha(regra, 100).explicacao)
    assert "Faixa 50-199" in texto
    assert "Frente e verso" in texto
    assert "Taxa de arte" in texto
    assert "Mínimo por linha" in texto


# ------------------------------------------------------------- endpoint V0


def _corpo_simulacao() -> dict:
    return {
        "quantidade": 120,
        "faixas": [
            {"qtd_min": 1, "qtd_max": 49, "preco_unitario": "1.00"},
            {"qtd_min": 50, "qtd_max": 199, "preco_unitario": "0.80"},
            {"qtd_min": 200, "qtd_max": None, "preco_unitario": "0.60"},
        ],
    }


def test_endpoint_simula_preco_sem_gravar(client, admin_token):
    from tests.conftest import auth

    resp = client.post(
        "/v1/variacoes/preco/simular",
        headers=auth(client, admin_token),
        json=_corpo_simulacao(),
    )
    assert resp.status_code == 200, resp.text
    dados = resp.json()["data"]
    assert dados["total"] == "96.00"
    assert dados["faixa"] == "50-199"
    assert any("Faixa 50-199" in linha for linha in dados["explicacao"])


def test_endpoint_sem_preco_devolve_codigo(client, admin_token):
    from tests.conftest import auth

    resp = client.post(
        "/v1/variacoes/preco/simular",
        headers=auth(client, admin_token),
        json={"quantidade": 10},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["codigo"] == "PRECO_NAO_CADASTRADO"


def test_endpoint_exige_autenticacao(client):
    resp = client.post("/v1/variacoes/preco/simular", json=_corpo_simulacao())
    assert resp.status_code == 401


def test_simulador_disponivel_em_modo_leitura(client, admin_token, monkeypatch):
    """É cálculo puro: continua disponível com a licença em modo leitura."""
    from tests.conftest import auth
    from app.services import licensa_service

    monkeypatch.setitem(licensa_service.ESTADO, "modo_leitura", True)
    try:
        resp = client.post(
            "/v1/variacoes/preco/simular",
            headers=auth(client, admin_token),
            json=_corpo_simulacao(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["total"] == "96.00"
    finally:
        monkeypatch.undo()
