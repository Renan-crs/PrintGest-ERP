"""Motor de precificação do M1 (PRD v3.0 §3.2.1) — casos canônicos do PRD.

Os exemplos do PRD são **casos fixos** (aceite §8.1): 100,00 → 230,00 →
243,80 e 87,35 → 200,91 → 212,96. O 87,35 é o canário do arredondamento: com o
padrão *banker's* do `Decimal` o CP sairia 200,90 e o exemplo quebraria — por
isso `ROUND_HALF_UP` é explícito. O atalho "VF × 2,438" diverge em borda
(0,05 → 0,13 sequencial, 0,12 direto) — a fórmula normativa é a sequencial.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services import precificacao
from tests.conftest import TEST_DB_URL, auth


@pytest.fixture()
def db_teste():
    engine = create_engine(TEST_DB_URL)
    with Session(engine) as sessao:
        yield sessao
    engine.dispose()


@pytest.fixture()
def _filial(db_teste) -> int:
    return int(
        db_teste.execute(text("SELECT id FROM filial ORDER BY id LIMIT 1")).scalar_one()
    )


@pytest.fixture(autouse=True)
def _sem_parametros_salvos(db_teste):
    """Hermeticidade: cada teste parte dos padrões (130/6), sem linhas salvas."""
    from app.models.config import PrecoParametro

    db_teste.query(PrecoParametro).delete()
    db_teste.commit()


# ------------------------------------------------------------- cálculo puro


@pytest.mark.parametrize(
    "vf,cp_esperado,vo_esperado",
    [
        (Decimal("100.00"), Decimal("230.00"), Decimal("243.80")),  # caso do PRD
        (Decimal("87.35"), Decimal("200.91"), Decimal("212.96")),  # canário do arredondamento
        (Decimal("0.05"), Decimal("0.12"), Decimal("0.13")),  # borda: atalho ×2,438 daria 0,12
        (Decimal("0.00"), Decimal("0.00"), Decimal("0.00")),
        (Decimal("1234.56"), Decimal("2839.49"), Decimal("3009.86")),
    ],
)
def test_vf_cp_vo_casos_canonicos(vf, cp_esperado, vo_esperado):
    cp = precificacao.calcular_cp(vf, Decimal("130"))
    vo = precificacao.calcular_vo(cp, Decimal("6"))
    assert cp == cp_esperado
    assert vo == vo_esperado


def test_vo_calculado_sobre_cp_ja_arredondado():
    """Fórmula normativa: sequencial — CP arredondado ANTES do VO (PRD §3.2.1)."""
    cp = precificacao.calcular_cp(Decimal("87.35"), Decimal("130"))
    assert cp == Decimal("200.91")  # 200,905 → meio para cima
    assert precificacao.calcular_vo(cp, Decimal("6")) == Decimal("212.96")


def test_markup_e_acrescimo_nao_margem_sobre_preco_final():
    """Q-01 decidida: 6% é acréscimo sobre o CP — a forma CP ÷ 0,94 está fora."""
    vo = precificacao.calcular_vo(Decimal("230.00"), Decimal("6"))
    assert vo == Decimal("243.80")
    assert vo != (Decimal("230.00") / Decimal("0.94")).quantize(Decimal("0.01"))


def test_percentuais_e_vf_negativos_sao_recusados():
    with pytest.raises(ValueError):
        precificacao.calcular_cp(Decimal("10"), Decimal("-1"))
    with pytest.raises(ValueError):
        precificacao.calcular_vo(Decimal("10"), Decimal("100000.01"))
    with pytest.raises(ValueError):
        precificacao.calcular_cp(Decimal("-0.01"), Decimal("130"))


def test_snapshot_do_item_guarda_o_que_foi_aplicado():
    """Snapshot (PRD §3.2.1): mudar o parâmetro depois não altera o item."""
    snap = precificacao.snapshot_item_terceirizado(Decimal("100.00"), Decimal("130"), Decimal("6"))
    assert snap == {
        "vf": "100.00",
        "acrescimo_fornecedor_pct": "130",
        "markup_orcamento_pct": "6",
        "cp": "230.00",
        "vo": "243.80",
    }
    # os valores vêm como texto — prontos para o snapshot da ordem_servico_item
    assert all(isinstance(v, str) for v in snap.values())


# ------------------------------------------------- parâmetros por filial


def test_parametros_padrao_sem_linhas(db_teste, _filial):
    pcts = precificacao.parametros(db_teste, filial_id=_filial)
    assert pcts == {
        "acrescimo_fornecedor_pct": Decimal("130"),
        "markup_orcamento_pct": Decimal("6"),
    }


def test_definir_parametros_grava_quem_e_quando(db_teste, _filial):
    pcts = precificacao.definir_parametros(
        db_teste,
        filial_id=_filial,
        usuario_id=1,
        dados={"acrescimo_fornecedor_pct": Decimal("150")},
    )
    assert pcts["acrescimo_fornecedor_pct"] == Decimal("150")
    assert pcts["markup_orcamento_pct"] == Decimal("6")  # intacto

    from app.models.config import PrecoParametro

    linha = (
        db_teste.query(PrecoParametro)
        .filter(PrecoParametro.chave == "acrescimo_fornecedor_pct")
        .one()
    )
    assert linha.usuario_id == 1
    assert linha.atualizado_em is not None

    # idempotente: reenviar o mesmo valor não cria linha nova
    precificacao.definir_parametros(
        db_teste, filial_id=_filial, usuario_id=1,
        dados={"markup_orcamento_pct": Decimal("6")},
    )
    assert db_teste.query(PrecoParametro).count() == 1


def test_calcular_item_usa_parametros_da_filial(db_teste, _filial):
    snap = precificacao.calcular_item_terceirizado(
        db_teste, filial_id=_filial, vf=Decimal("100.00")
    )
    assert snap["vo"] == "243.80"

    precificacao.definir_parametros(
        db_teste, filial_id=_filial, usuario_id=1,
        dados={"markup_orcamento_pct": Decimal("10")},
    )
    snap = precificacao.calcular_item_terceirizado(
        db_teste, filial_id=_filial, vf=Decimal("100.00")
    )
    assert snap["cp"] == "230.00"
    assert snap["vo"] == "253.00"  # 230 × 1,10


# --------------------------------------------------------------- endpoint


def test_endpoint_precificacao_le_defaults_e_altera(client, admin_token):
    resp = client.get("/v1/config/precificacao", headers=auth(client, admin_token))
    assert resp.status_code == 200, resp.text
    corpo = resp.json()["data"]
    assert Decimal(corpo["acrescimo_fornecedor_pct"]) == Decimal("130")
    assert Decimal(corpo["markup_orcamento_pct"]) == Decimal("6")

    resp = client.put(
        "/v1/config/precificacao",
        headers=auth(client, admin_token),
        json={"acrescimo_fornecedor_pct": "140", "markup_orcamento_pct": "8"},
    )
    assert resp.status_code == 200, resp.text
    corpo = resp.json()["data"]
    assert Decimal(corpo["acrescimo_fornecedor_pct"]) == Decimal("140")
    assert Decimal(corpo["markup_orcamento_pct"]) == Decimal("8")

    # persistiu: uma segunda leitura devolve o valor alterado
    resp = client.get("/v1/config/precificacao", headers=auth(client, admin_token))
    assert Decimal(resp.json()["data"]["markup_orcamento_pct"]) == Decimal("8")


def test_endpoint_rejeita_percentual_negativo(client, admin_token):
    resp = client.put(
        "/v1/config/precificacao",
        headers=auth(client, admin_token),
        json={"markup_orcamento_pct": "-1"},
    )
    assert resp.status_code == 422


def test_endpoint_somente_admin(client, admin_token):
    """Permissão `alterar_parametros_precificacao` = Admin (PRD §3.2.3)."""
    from app.models.enums import NivelAcesso
    from tests.test_rbac import _criar_usuario, _login_usuario

    login, senha = _criar_usuario(client, admin_token, NivelAcesso.OPERADOR)
    token = _login_usuario(client, login, senha)

    resp = client.get("/v1/config/precificacao", headers=auth(client, token))
    assert resp.status_code == 403
