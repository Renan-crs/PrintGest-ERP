"""Módulo Cadastro de Fornecedores (mockup 2.3) sobre a base `PaginaCrud`.

Colunas do grid seguem o mockup: Razão Social / Nome Fantasia, CNPJ,
Cidade/UF, Principais Insumos, Representante Comercial, Telefone / WhatsApp,
Cond. Pagto e Status. O formulário guarda dados cadastrais, contato comercial e
endereço. (Cotações ficam para a etapa de Compras.)
"""

from __future__ import annotations

from printgest.core.api import Api
from printgest.ui.formulario import (
    MASCARA_CEP,
    MASCARA_CNPJ,
    MASCARA_UF,
    CampoArea,
    CampoCombo,
    CampoTexto,
    limpo,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud

ENTIDADE = "fornecedores"

CHAVES = ["id", "nome_razao", "cpf_cnpj", "local", "representante", "contato"]
COLUNAS = ["Cód.", "Razão Social", "CNPJ", "Cidade/UF", "Representante", "Tel / WhatsApp"]

# Observação: os mockups mostram colunas de "Principais Insumos" e "Cond. Pagto",
# mas o contrato do RedGest não tem esses campos — eles ficam em `observacoes`.


class PaginaFornecedores(PaginaCrud):
    ENTIDADE = ENTIDADE
    ROTULO_PAGINA = "Cadastro de Fornecedores"
    ROTULO_NOVO = "Novo Fornecedor"
    GRUPO_LISTA = "FORNECEDORES E LINHAS DE INSUMO"
    CHAVES = CHAVES
    COLUNAS = COLUNAS
    LUGAR_BUSCA = "Buscar por razão social, CNPJ, telefone ou representante..."
    CAMPO_NOME = "nome_razao"

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._tipo = CampoCombo(
            "Tipo de Pessoa",
            [("pj", "Pessoa Jurídica"), ("pf", "Pessoa Física")],
            padrao="pj",
        )
        self._nome = CampoTexto("Razão Social / Nome Fantasia", maximo=200).obrigatorio()
        self._cnpj = CampoTexto("CNPJ / CPF", mono=True, maximo=18, mascara=MASCARA_CNPJ)
        self._ie = CampoTexto("Inscrição Estadual", mono=True, maximo=20)
        self._representante = CampoTexto("Representante Comercial", maximo=120)
        self._email = CampoTexto("E-mail", maximo=120)
        self._telefone = CampoTexto("Telefone", mono=True, maximo=20)
        self._celular = CampoTexto("Celular / WhatsApp", mono=True, maximo=20)
        self._obs = CampoArea("Observações (insumos / cond. pagto)", linhas=3)

        self._logradouro = CampoTexto("Logradouro", maximo=160)
        self._numero = CampoTexto("Número", maximo=12)
        self._complemento = CampoTexto("Complemento", maximo=80)
        self._bairro = CampoTexto("Bairro", maximo=80)
        self._cidade = CampoTexto("Cidade", maximo=80)
        self._uf = CampoTexto("UF", mono=True, maximo=2, mascara=MASCARA_UF)
        self._cep = CampoTexto("CEP", mono=True, maximo=8, mascara=MASCARA_CEP)

        return [
            (
                "Dados Cadastrais",
                [
                    self._tipo,
                    self._nome,
                    self._cnpj,
                    self._ie,
                    self._representante,
                    self._email,
                    self._telefone,
                    self._celular,
                    self._obs,
                ],
            ),
            (
                "Endereço",
                [
                    self._logradouro,
                    self._numero,
                    self._complemento,
                    self._bairro,
                    self._cidade,
                    self._uf,
                    self._cep,
                ],
            ),
        ]

    def _padroes_do_form(self) -> None:
        self._tipo.definir("pj")

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "id":
            ident = dado.get("id")
            return f"#{ident:05d}" if isinstance(ident, int) else ""
        if chave == "local":
            return f"{dado.get('cidade', '')}/{dado.get('uf', '')}".strip("/")
        if chave == "representante":
            return dado.get("contato_nome") or ""
        if chave == "contato":
            return dado.get("celular") or dado.get("telefone") or ""
        return super()._formatar_texto(dado, chave)

    def _preencher_campos(self, dado: dict) -> None:
        self._tipo.definir(dado.get("tipo_pessoa") or "pj")
        self._nome.definir(dado.get("nome_razao"))
        self._cnpj.definir(dado.get("cpf_cnpj"))
        self._ie.definir(dado.get("inscricao_estadual"))
        self._representante.definir(dado.get("contato_nome"))
        self._email.definir(dado.get("email"))
        self._telefone.definir(dado.get("telefone"))
        self._celular.definir(dado.get("celular"))
        self._obs.definir(dado.get("observacoes"))
        self._logradouro.definir(dado.get("logradouro"))
        self._numero.definir(dado.get("numero"))
        self._complemento.definir(dado.get("complemento"))
        self._bairro.definir(dado.get("bairro"))
        self._cidade.definir(dado.get("cidade"))
        self._uf.definir(dado.get("uf"))
        self._cep.definir(dado.get("cep"))

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._nome.valido():
            return ("Informe a razão social / nome fantasia.", self._nome)
        return None

    def _payload(self) -> dict:
        return {
            "tipo_pessoa": self._tipo.valor(),
            "nome_razao": self._nome.valor(),
            "cpf_cnpj": limpo(self._cnpj.valor()),
            "inscricao_estadual": limpo(self._ie.valor()),
            "contato_nome": limpo(self._representante.valor()),
            "email": limpo(self._email.valor()),
            "telefone": limpo(self._telefone.valor()),
            "celular": limpo(self._celular.valor()),
            "observacoes": limpo(self._obs.valor()),
            "logradouro": limpo(self._logradouro.valor()),
            "numero": limpo(self._numero.valor()),
            "complemento": limpo(self._complemento.valor()),
            "bairro": limpo(self._bairro.valor()),
            "cidade": limpo(self._cidade.valor()),
            "uf": limpo(self._uf.valor()),
            "cep": limpo(self._cep.valor()),
        }