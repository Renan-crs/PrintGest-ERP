"""Módulo Cadastro de Clientes (mockup 2.1) sobre a base `PaginaCrud`."""

from __future__ import annotations

from printgest.ui.endereco import BlocoEndereco
from printgest.ui.formulario import (
    MASCARA_CNPJ,
    MASCARA_CPF,
    CampoArea,
    CampoArquivo,
    CampoCheck,
    CampoCombo,
    CampoData,
    CampoTexto,
    CampoValor,
    data_iso,
    limpo,
    numero,
    primeiro_valor,
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
    PESOS = [1, 1, 5, 3, 3, 1]
    FILTROS = FILTROS
    CHAVE_FILTRO = "tipo_pessoa"
    LUGAR_BUSCA = "Buscar por nome, razão social, CNPJ/CPF, telefone ou e-mail..."
    CAMPO_NOME = "nome_razao"
    VAZIO = "Nenhum cliente encontrado. Clique em Novo Cliente (F6)."

    # ----------------------------------------------------------- formulário

    def _secoes(self):
        self._tipo = CampoCombo(
            "Tipo de Pessoa",
            [("pf", "Pessoa Física"), ("pj", "Pessoa Jurídica")],
            padrao="pf",
        )
        self._nome = CampoTexto("Nome / Razão Social", maximo=200).obrigatorio().larga()
        self._doc = CampoTexto("CPF / CNPJ", mono=True, maximo=18, mascara=MASCARA_CPF)
        self._ie = CampoTexto("Inscrição Estadual", mono=True, maximo=20)
        self._nasc = CampoData("Data de Nascimento")
        self._email = CampoTexto("E-mail", maximo=120).larga()
        self._telefone = CampoTexto("Telefone", mono=True, maximo=20)
        self._celular = CampoTexto("Celular / WhatsApp", mono=True, maximo=20)
        self._obs = CampoArea("", linhas=2).larga()
        self._foto = CampoArquivo("Foto do Cliente").larga()

        self._adiantado = CampoCheck("Pagamento adiantado (total)")
        self._sinal = CampoCheck("Sinal")
        self._sinal_pct = CampoValor("Percentual do Sinal", prefixo="%")

        self._end = BlocoEndereco()

        return [
            (
                "Dados Gerais",
                [
                    self._tipo,
                    self._doc,
                    self._nome,
                    self._ie,
                    self._nasc,
                    self._email,
                    self._telefone,
                    self._celular,
                    self._foto,
                ],
            ),
            ("Endereço & Entrega", self._end.campos),
            ("Observações", [self._obs]),
            (
                "Condições de Pagamento",
                [self._adiantado, self._sinal, self._sinal_pct],
            ),
        ]

    def _conectar_campos(self) -> None:
        self._tipo.widget.currentIndexChanged.connect(self._tipo_mudou)
        self._adiantado.widget.toggled.connect(self._so_adiantado)
        self._sinal.widget.toggled.connect(self._so_sinal)
        self._tipo_mudou()
        self._atualizar_sinal()

    def _tipo_mudou(self) -> None:
        pf = self._tipo.valor() == "pf"
        self._doc.definir_mascara(MASCARA_CPF if pf else MASCARA_CNPJ)
        # Data de nascimento só faz sentido para pessoa física; IE para jurídica.
        self._nasc.visivel(pf)
        self._ie.visivel(not pf)

    def _so_adiantado(self, ligado: bool) -> None:
        # Condições mutuamente exclusivas: pagamento adiantado OU sinal.
        if ligado and self._sinal.valor():
            self._sinal.definir(False)
        self._atualizar_sinal()

    def _so_sinal(self, ligado: bool) -> None:
        if ligado and self._adiantado.valor():
            self._adiantado.definir(False)
        self._atualizar_sinal()

    def _atualizar_sinal(self) -> None:
        self._sinal_pct.widget.setEnabled(self._sinal.valor() and not self._modo_leitura)

    # -------------------------------------------------------------- leitura

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "tipo_pessoa":
            return str(dado.get("tipo_pessoa", "")).upper()
        if chave == "contato":
            return primeiro_valor(dado, "celular", "telefone")
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
        self._foto.definir(dado.get("foto_path"))
        self._adiantado.definir(dado.get("pagamento_adiantado"))
        self._sinal.definir(dado.get("sinal"))
        self._sinal_pct.definir(dado.get("sinal_pct"))
        self._end.preencher(dado)

    def _padroes_do_form(self) -> None:
        self._tipo.definir("pf")
        self._doc.definir_mascara(MASCARA_CPF)
        self._sinal_pct.definir("50")
        self._atualizar_sinal()

    # ---------------------------------------------------------------- salvar

    def _validar(self):
        if not self._nome.valido():
            return ("Informe o nome / razão social.", self._nome)
        if self._adiantado.valor() and self._sinal.valor():
            return (
                "Escolha apenas uma condição: pagamento adiantado OU sinal.",
                self._sinal,
            )
        if self._sinal.valor():
            pct = self._sinal_pct.valor()
            if pct is None or pct <= 0 or pct > 100:
                return ("Informe um percentual de sinal entre 0 e 100.", self._sinal_pct)
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
            "foto_path": limpo(self._foto.valor()),
            "pagamento_adiantado": self._adiantado.valor(),
            "sinal": self._sinal.valor(),
            "sinal_pct": numero(self._sinal_pct, "50"),
            **self._end.payload(),
        }
