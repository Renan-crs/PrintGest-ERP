"""Módulo Cadastro de Clientes (mockup 2.1) sobre a base `PaginaCrud`."""

from __future__ import annotations

from printgest.core.api import Api
from printgest.ui.formulario import (
    MASCARA_CEP,
    MASCARA_CNPJ,
    MASCARA_CPF,
    MASCARA_UF,
    CampoArea,
    CampoCombo,
    CampoData,
    CampoTexto,
    data_iso,
    limpo,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud

ENTIDADE = "clientes"

CHAVES = ["id", "tipo_pessoa", "nome_razao", "cpf_cnpj", "contato", "_acoes"]
COLUNAS = ["ID", "Tipo", "Cliente / Razão Social", "Documento", "Contato", "Ações"]

FILTROS = [("", "Todos"), ("pf", "Pessoa Física"), ("pj", "Pessoa Jurídica")]


class PaginaClientes(PaginaCrud):
    ENTIDADE = ENTIDADE
    ROTULO_PAGINA = "Cadastro de Clientes"
    ROTULO_NOVO = "Novo Cliente"
    GRUPO_LISTA = "REGISTROS DE BALCÃO E CONTRATOS"
    CHAVES = CHAVES
    COLUNAS = COLUNAS
    FILTROS = FILTROS
    CHAVE_FILTRO = "tipo_pessoa"
    LUGAR_BUSCA = "Buscar por nome, razão social, CNPJ/CPF, telefone ou e-mail..."
    CAMPO_NOME = "nome_razao"

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._tipo = CampoCombo(
            "Tipo de Pessoa",
            [("pf", "Pessoa Física"), ("pj", "Pessoa Jurídica")],
            padrao="pf",
        )
        self._nome = CampoTexto("Nome / Razão Social", maximo=200).obrigatorio()
        self._doc = CampoTexto("CPF / CNPJ", mono=True, maximo=18, mascara=MASCARA_CPF)
        self._ie = CampoTexto("Inscrição Estadual", mono=True, maximo=20)
        self._nasc = CampoData("Data de Nascimento")
        self._email = CampoTexto("E-mail", maximo=120)
        self._telefone = CampoTexto("Telefone", mono=True, maximo=20)
        self._celular = CampoTexto("Celular / WhatsApp", mono=True, maximo=20)
        self._obs = CampoArea("Observações Técnicas", linhas=2)

        self._logradouro = CampoTexto("Logradouro", maximo=160)
        self._numero = CampoTexto("Número", maximo=12)
        self._complemento = CampoTexto("Complemento", maximo=80)
        self._bairro = CampoTexto("Bairro", maximo=80)
        self._cidade = CampoTexto("Cidade", maximo=80)
        self._uf = CampoTexto("UF", mono=True, maximo=2, mascara=MASCARA_UF)
        self._cep = CampoTexto("CEP", mono=True, maximo=8, mascara=MASCARA_CEP)

        return [
            (
                "Dados Gerais",
                [
                    self._tipo,
                    self._nome,
                    self._doc,
                    self._ie,
                    self._nasc,
                    self._email,
                    self._telefone,
                    self._celular,
                    self._obs,
                ],
            ),
            (
                "Endereço & Entrega",
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

    def _conectar_campos(self) -> None:
        self._tipo.widget.currentIndexChanged.connect(self._tipo_mudou)

    def _tipo_mudou(self) -> None:
        self._doc.definir_mascara(MASCARA_CNPJ if self._tipo.valor() == "pj" else MASCARA_CPF)

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "id":
            ident = dado.get("id")
            return f"#{ident:05d}" if isinstance(ident, int) else ""
        if chave == "tipo_pessoa":
            return str(dado.get("tipo_pessoa", "")).upper()
        if chave == "contato":
            return dado.get("celular") or dado.get("telefone") or ""
        if chave == "_acoes":
            return ""
        return super()._formatar_texto(dado, chave)

    def _preencher_campos(self, dado: dict) -> None:
        self._tipo.definir(dado.get("tipo_pessoa"))
        self._nome.definir(dado.get("nome_razao"))
        self._doc.definir(dado.get("cpf_cnpj"))
        self._ie.definir(dado.get("inscricao_estadual"))
        self._nasc.definir(dado.get("data_nascimento"))
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

    def _padroes_do_form(self) -> None:
        self._tipo.definir("pf")
        self._doc.definir_mascara(MASCARA_CPF)

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._nome.valido():
            return ("Informe o nome / razão social.", self._nome)
        return None

    def _payload(self) -> dict:
        return {
            "tipo_pessoa": self._tipo.valor(),
            "nome_razao": self._nome.valor(),
            "cpf_cnpj": limpo(self._doc.valor()),
            "inscricao_estadual": limpo(self._ie.valor()),
            "data_nascimento": data_iso(self._nasc.valor()),
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