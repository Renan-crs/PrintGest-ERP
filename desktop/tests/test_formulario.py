"""Testes dos helpers de formulário (parsing monetário, datas, texto)."""

from __future__ import annotations

from decimal import Decimal

from printgest.ui.formulario import (
    CampoCheck,
    CampoTelefone,
    CampoTexto,
    formatar_data_iso,
    formatar_telefone,
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


# --------------------------------------------------------- máscaras de entrada


def test_formatar_telefone_aceita_fixo_e_celular():
    assert formatar_telefone("1132221100") == "(11) 3222-1100"
    assert formatar_telefone("11988221100") == "(11) 98822-1100"
    assert formatar_telefone("(11) 98822-1100") == "(11) 98822-1100"
    assert formatar_telefone("11") == "(11"
    assert formatar_telefone("1198") == "(11) 98"
    assert formatar_telefone("1198221") == "(11) 9822-1"
    assert formatar_telefone("") == ""
    assert formatar_telefone(None) == ""
    assert formatar_telefone("--") == ""
    # Excesso é descartado, não corrompe o resto.
    assert formatar_telefone("119882211001234") == "(11) 98822-1100"


def test_campo_telefone_formata_ao_digitar(app):
    campo = CampoTelefone("Telefone")
    campo.widget.setText("11988221100")
    assert campo.valor() == "(11) 98822-1100"
    campo.definir("1130000000")
    assert campo.valor() == "(11) 3000-0000"
    campo.definir(None)
    assert campo.valor() == ""
    assert campo.widget.text() == ""


def test_campo_texto_caixa_alta_normaliza_uf(app):
    campo = CampoTexto("UF", maximo=2, caixa_alta=True)
    campo.widget.setText("sp")
    assert campo.valor() == "SP"
    assert campo.widget.text() == "SP"


def test_campo_mascarado_vazio_retorna_vazio(app):
    from printgest.ui.formulario import MASCARA_CEP, MASCARA_CNPJ

    assert CampoTexto("CEP", mascara=MASCARA_CEP).valor() == ""
    assert CampoTexto("CNPJ", mascara=MASCARA_CNPJ).valor() == ""


def test_cep_mascarado_sai_apenas_com_digitos(app):
    # CHAR(8) no banco: "01310-100" (9 chars) seria rejeitado pelo schema.
    from printgest.ui.formulario import MASCARA_CEP

    campo = CampoTexto("CEP", maximo=8, mascara=MASCARA_CEP, apenas_digitos=True)
    campo.widget.setText("01310100")
    assert campo.widget.text() == "01310-100"  # máscara é só visual
    assert campo.valor() == "01310100"  # valor sai com 8 dígitos


def test_campo_apenas_digitos_aceita_texto_colidado(app):
    # CNPJ colado formatado ("12.345.678/0001-99") vira os 14 dígitos do CHAR(14).
    campo = CampoTexto("CNPJ", maximo=14, apenas_digitos=True)
    campo.widget.setText("12.345.678/0001-99")
    assert campo.valor() == "12345678000199"
    campo.widget.setText("")
    assert campo.valor() == ""
