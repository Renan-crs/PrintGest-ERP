"""Módulo Cadastro de Funcionários sobre a base `PaginaCrud`.

Sem mockup dedicado (o mockup 2.4 é Usuários/RBAC); segue o padrão dos demais
cadastros. Campos conforme `FuncionarioBase`: dados pessoais, vínculo, papéis de
atendimento (vendedor/atendente/produção) e comissão.
"""

from __future__ import annotations

from printgest.ui.formulario import (
    MASCARA_CPF,
    CampoArea,
    CampoCheck,
    CampoData,
    CampoTelefone,
    CampoTexto,
    CampoValor,
    data_iso,
    limpo,
    numero,
    primeiro_valor,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud

ENTIDADE = "funcionarios"

CHAVES = ["id", "nome", "cargo", "cpf", "contato", "funcoes"]
COLUNAS = ["Cód.", "Funcionário", "Cargo", "CPF", "Contato", "Funções"]


class PaginaFuncionarios(PaginaCrud):
    ENTIDADE = ENTIDADE
    ROTULO_PAGINA = "Cadastro de Funcionários"
    ROTULO_NOVO = "Novo Funcionário"
    GRUPO_LISTA = "EQUIPE DA GRÁFICA"
    CHAVES = CHAVES
    COLUNAS = COLUNAS
    LUGAR_BUSCA = "Buscar por nome, cargo ou CPF..."
    CAMPO_NOME = "nome"

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._nome = CampoTexto("Nome Completo", maximo=120).obrigatorio()
        self._cpf = CampoTexto("CPF", mono=True, maximo=14, mascara=MASCARA_CPF)
        self._nascimento = CampoData("Data de Nascimento")
        self._email = CampoTexto("E-mail", maximo=120)
        self._telefone = CampoTelefone("Telefone")

        self._cargo = CampoTexto("Cargo / Função", maximo=60)
        self._admissao = CampoData("Data de Admissão")
        self._comissao = CampoValor("Comissão (%)", prefixo="%")

        self._e_vendedor = CampoCheck("Vendedor")
        self._e_atendente = CampoCheck("Atendente")
        self._e_producao = CampoCheck("Produção")
        self._obs = CampoArea("Observações", linhas=2)

        return [
            (
                "Dados Pessoais",
                [
                    self._nome,
                    self._cpf,
                    self._nascimento,
                    self._email,
                    self._telefone,
                ],
            ),
            (
                "Vínculo & Função",
                [self._cargo, self._admissao, self._comissao],
            ),
            (
                "Papéis no Atendimento",
                [self._e_vendedor, self._e_atendente, self._e_producao, self._obs],
            ),
        ]

    def _padroes_do_form(self) -> None:
        self._comissao.definir("0")

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "contato":
            return primeiro_valor(dado, "telefone", "email")
        if chave == "funcoes":
            papéis = [
                rot for rot, ligado in
                (("Vend.", dado.get("e_vendedor")), ("Atend.", dado.get("e_atendente")), ("Prod.", dado.get("e_producao")))
                if ligado
            ]
            return " / ".join(papéis)
        if chave == "nome":
            return dado.get("nome") or ""
        return super()._formatar_texto(dado, chave)

    def _preencher_campos(self, dado: dict) -> None:
        self._nome.definir(dado.get("nome"))
        self._cpf.definir(dado.get("cpf"))
        self._nascimento.definir(dado.get("data_nascimento"))
        self._email.definir(dado.get("email"))
        self._telefone.definir(dado.get("telefone"))
        self._cargo.definir(dado.get("cargo"))
        self._admissao.definir(dado.get("data_admissao"))
        self._comissao.definir(dado.get("comissao_pct"))
        self._e_vendedor.definir(dado.get("e_vendedor"))
        self._e_atendente.definir(dado.get("e_atendente"))
        self._e_producao.definir(dado.get("e_producao"))
        self._obs.definir(dado.get("observacoes"))

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._nome.valido():
            return ("Informe o nome do funcionário.", self._nome)
        return None

    def _payload(self) -> dict:
        return {
            "nome": self._nome.valor(),
            "cpf": limpo(self._cpf.valor()),
            "cargo": limpo(self._cargo.valor()),
            "email": limpo(self._email.valor()),
            "telefone": limpo(self._telefone.valor()),
            "data_nascimento": data_iso(self._nascimento.valor()),
            "data_admissao": data_iso(self._admissao.valor()),
            "e_vendedor": self._e_vendedor.valor(),
            "e_atendente": self._e_atendente.valor(),
            "e_producao": self._e_producao.valor(),
            "comissao_pct": numero(self._comissao),
            "observacoes": limpo(self._obs.valor()),
        }
