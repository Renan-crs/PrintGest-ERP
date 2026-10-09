"""Bloco reutilizável de endereço (clientes e fornecedores).

Concentra a criação dos sete campos, o preenchimento a partir do registro da API
e a montagem do payload — antes cada cadastro repetia o mesmo bloco três vezes.
"""

from __future__ import annotations

from printgest.ui.formulario import (
    MASCARA_CEP,
    MASCARA_UF,
    CampoTexto,
    limpo,
)


class BlocoEndereco:
    """Campos de endereço com `campos` (para `_secoes`/grade), `preencher` e `payload`."""

    def __init__(self) -> None:
        self.logradouro = CampoTexto("Logradouro", maximo=160)
        self.numero = CampoTexto("Número", maximo=12)
        self.complemento = CampoTexto("Complemento", maximo=80)
        self.bairro = CampoTexto("Bairro", maximo=80)
        self.cidade = CampoTexto("Cidade", maximo=80)
        self.uf = CampoTexto("UF", mono=True, maximo=2, mascara=MASCARA_UF)
        self.cep = CampoTexto("CEP", mono=True, maximo=8, mascara=MASCARA_CEP)

    @property
    def campos(self) -> list:
        return [
            self.logradouro,
            self.numero,
            self.complemento,
            self.bairro,
            self.cidade,
            self.uf,
            self.cep,
        ]

    def preencher(self, dado: dict) -> None:
        self.logradouro.definir(dado.get("logradouro"))
        self.numero.definir(dado.get("numero"))
        self.complemento.definir(dado.get("complemento"))
        self.bairro.definir(dado.get("bairro"))
        self.cidade.definir(dado.get("cidade"))
        self.uf.definir(dado.get("uf"))
        self.cep.definir(dado.get("cep"))

    def payload(self) -> dict:
        return {
            "logradouro": limpo(self.logradouro.valor()),
            "numero": limpo(self.numero.valor()),
            "complemento": limpo(self.complemento.valor()),
            "bairro": limpo(self.bairro.valor()),
            "cidade": limpo(self.cidade.valor()),
            "uf": limpo(self.uf.valor()),
            "cep": limpo(self.cep.valor()),
        }
