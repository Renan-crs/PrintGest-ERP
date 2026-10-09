"""Testes dos helpers de formulário (parsing monetário, datas, texto)."""

from __future__ import annotations

from decimal import Decimal

from printgest.ui.formulario import (
    CampoCheck,
    formatar_data_iso,
    limpo,
    numero,
    para_decimal,
)


class _Campo:
    """Dublê mínimo de campo com `.valor()`."""

    def __init__(self, valor):
        self._valor = valor

    def valor(self):
        return self._valor


def test_para_decimal_aceita_formato_brasileiro():
    assert para_decimal("1.500,00") == Decimal("1500.00")
    assert para_decimal("R$ 1.234,56") == Decimal("1234.56")
    assert para_decimal("84,70") == Decimal("84.70")
    assert para_decimal("38") == Decimal("38")


def test_para_decimal_invalido_vira_none():
    assert para_decimal("") is None
    assert para_decimal("   ") is None
    assert para_decimal("abc") is None
    assert para_decimal(None) is None


def test_limpo_remove_texto_vazio():
    assert limpo("") is None
    assert limpo("   ") is None
    assert limpo("x") == "x"
    assert limpo(None) is None
    assert limpo(0) == 0


def test_numero_usa_padrao_quando_none():
    assert numero(_Campo(None)) == "0"
    assert numero(_Campo(None), "1") == "1"
    assert numero(_Campo(5)) == "5"


def test_formatar_data_iso():
    assert formatar_data_iso("2026-09-25") == "25/09/2026"
    assert formatar_data_iso("2026-09-25T12:30:00") == "25/09/2026"
    assert formatar_data_iso(None) == ""
    assert formatar_data_iso("") == ""
    assert formatar_data_iso("inválida") == ""


def test_campo_check_nao_duplica_rotulo(app):
    # O texto fica só no próprio checkbox (sem QLabel de campo repetindo-o).
    campo = CampoCheck("Sinal")
    assert campo.rotulo_widget is None
    assert campo.widget.text() == "Sinal"
    assert campo.valor() is False
