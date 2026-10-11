"""Módulo Cadastro de Fornecedores (mockup 2.3) sobre a base `PaginaCrud`.

Colunas do grid seguem o mockup: Razão Social / Nome Fantasia, CNPJ,
Cidade/UF, Principais Insumos, Representante Comercial, Telefone / WhatsApp,
Cond. Pagto e Status. O formulário guarda dados cadastrais, contato comercial e
endereço. (Cotações ficam para a etapa de Compras.)
"""

from __future__ import annotations

from printgest.ui.endereco import BlocoEndereco
from printgest.ui.formulario import (
    MASCARA_CNPJ,
    MASCARA_CPF,
    CampoArea,
    CampoCombo,
    CampoTexto,
    limpo,
    primeiro_valor,
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
    PESOS = [1, 5, 3, 3, 3, 3]
    LUGAR_BUSCA = "Buscar por razão social, CNPJ, telefone ou representante..."
    CAMPO_NOME = "nome_razao"
    VAZIO = "Nenhum fornecedor encontrado. Clique em Novo Fornecedor (F6)."

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._tipo = CampoCombo(
            "Tipo de Pessoa",
            [("pj", "Pessoa Jurídica"), ("pf", "Pessoa Física")],
            padrao="pj",
        )
        self._nome = (
            CampoTexto("Razão Social / Nome Fantasia", maximo=200).obrigatorio().larga()
        )
        self._cnpj = CampoTexto("CNPJ / CPF", mono=True, maximo=18, mascara=MASCARA_CNPJ)
        self._ie = CampoTexto("Inscrição Estadual", mono=True, maximo=20)
        self._representante = CampoTexto("Representante Comercial", maximo=120)
        self._email = CampoTexto("E-mail", maximo=120).larga()
        self._telefone = CampoTexto("Telefone", mono=True, maximo=20)
        self._celular = CampoTexto("Celular / WhatsApp", mono=True, maximo=20)
        self._obs = CampoArea("", linhas=3).larga()

        self._end = BlocoEndereco()

        return [
            (
                "Dados Cadastrais",
                [
                    self._tipo,
                    self._cnpj,
                    self._nome,
                    self._ie,
                    self._representante,
                    self._email,
                    self._telefone,
                    self._celular,
                ],
            ),
            ("Endereço", self._end.campos),
            ("Observações", [self._obs]),
        ]

    def _conectar_campos(self) -> None:
        self._tipo.widget.currentIndexChanged.connect(self._tipo_mudou)
        self._tipo_mudou()

    def _tipo_mudou(self) -> None:
        pj = self._tipo.valor() == "pj"
        self._cnpj.definir_mascara(MASCARA_CNPJ if pj else MASCARA_CPF)
        self._ie.visivel(pj)

    def _padroes_do_form(self) -> None:
        self._tipo.definir("pj")

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "local":
            return f"{dado.get('cidade', '')}/{dado.get('uf', '')}".strip("/")
        if chave == "representante":
            return dado.get("contato_nome") or ""
        if chave == "contato":
            return primeiro_valor(dado, "celular", "telefone")
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
        self._end.preencher(dado)

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
            **self._end.payload(),
        }
