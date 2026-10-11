"""Módulo Configuração (PRD §1.8 / telas_e_fluxos §1.8, §2.6) — exclusivo do admin.

Quatro sub-abas:
  - **Dados da Empresa** (`PaginaEmpresa`)  — ficha única da `empresa`.
  - **Personalização** (`PaginaPersonalizacao`) — logotipo/fundo/impressoras.
  - **Reajuste de Preços** (`PaginaReajuste`) — prévia + confirmação por senha.
  - **Usuários e Níveis** (`PaginaUsuarios`) — CRUD de `/v1/usuarios`.

Padrões herdados dos Cadastros/Financeiro/Fiscal: grade densa, formulário em
painel, rodapé fixo, estados vazios e atalhos sem conflito (F10 salva, Esc
reverte; no Reajuste, F8 simula e F9 aplica). Escrita bloqueada em modo leitura.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from printgest.core import catalogos
from printgest.core.api import Api
from printgest.core.rbac import pode_abrir
from printgest.core.tarefas import rodar
from printgest.ui.formulario import (
    CampoArquivo,
    CampoCheck,
    CampoCombo,
    CampoTexto,
    CampoValor,
    dispor_campos,
    formatar_data_hora,
    formatar_moeda,
    formatar_percentual,
    grade_campos,
    limpo,
    rotulo_secao,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import ElideLabel, badge, botao_com_atalho

_NIVEIS = [
    ("admin", "Administrador"),
    ("gerente", "Gerente"),
    ("operador", "Operador"),
    ("caixa", "Caixa"),
]
_NIVEL_ROTULO = dict(_NIVEIS)


# =============================================================== ficha única


class PaginaFicha(QWidget):
    """Ficha de registro único (sem lista): seções roláveis + rodapé fixo.

    Base de Dados da Empresa e Personalização. O rodapé fica **fora** da área
    rolável (como no `PaginaCrud`), com Reverter (Esc) e Salvar (F10).
    """

    ROTULO_PAGINA = "Ficha"
    ROTULO_SALVAR = "Salvar Alterações"

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._secoes_lista = self._secoes()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(10)
        raiz.addWidget(self._barra_titulo())

        if self._modo_leitura:
            aviso = QLabel("Modo leitura: consulta habilitada, escrita bloqueada.")
            aviso.setObjectName("bannerLeitura")
            raiz.addWidget(aviso)

        self._painel_form = QScrollArea()
        self._painel_form.setWidgetResizable(True)
        self._painel_form.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        raiz.addWidget(self._painel_form, 1)

        conteudo = QWidget()
        col = QVBoxLayout(conteudo)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        for titulo_secao, campos in self._secoes_lista:
            if titulo_secao:
                col.addWidget(rotulo_secao(titulo_secao))
            grade = grade_campos()
            dispor_campos(grade, campos)
            col.addLayout(grade)
        col.addStretch(1)
        self._painel_form.setWidget(conteudo)

        rodape = QWidget()
        rodape.setObjectName("rodape")
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(0, 0, 0, 0)
        self._status = QLabel("")
        self._status.setObjectName("subtitulo")
        rl.addWidget(self._status, 1)
        reverter, self._btn_reverter = botao_com_atalho("Reverter", "Esc")
        salvar, self._btn_salvar = botao_com_atalho(self.ROTULO_SALVAR, "F10", "primary")
        rl.addWidget(reverter)
        rl.addWidget(salvar)
        raiz.addWidget(rodape)

        self._btn_reverter.clicked.connect(self._reverter)
        self._btn_salvar.clicked.connect(self._salvar)
        QShortcut(QKeySequence("F10"), self, self._salvar)
        QShortcut(QKeySequence("Esc"), self, self._reverter)

        self._aplicar_modo_leitura()
        self._carregar()

    # ------------------------------------------------------------ construção

    def _barra_titulo(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        titulo = ElideLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        linha.addWidget(titulo, 1)
        for extra in self._badges_barra():
            linha.addWidget(extra)
        return caixa

    def _badges_barra(self) -> list:
        return []

    def _campos(self) -> list:
        return [campo for _titulo, campos in self._secoes_lista for campo in campos]

    def _aplicar_modo_leitura(self) -> None:
        for campo in self._campos():
            campo.habilitar(not self._modo_leitura)
        self._btn_salvar.setEnabled(not self._modo_leitura)
        self._btn_reverter.setEnabled(True)  # recarregar continua sendo leitura

    # -------------------------------------------------------------- carregar

    def _carregar(self) -> None:
        self._status.setText("Carregando…")
        rodar(self._buscar, on_ok=self._recebido, on_erro=self._erro_carga)

    def _recebido(self, dado: dict) -> None:
        self._preencher(dado or {})
        self._status.setText("")

    def _erro_carga(self, msg: str) -> None:
        self._status.setText("")
        QMessageBox.warning(self, "Configuração", msg)

    def _reverter(self) -> None:
        self._carregar()

    # ---------------------------------------------------------------- salvar

    def _salvar(self) -> None:
        if self._modo_leitura:
            return
        problema = self._validar()
        if problema:
            msg, campo = problema
            QMessageBox.warning(self, "Validação", msg)
            campo.widget.setFocus()
            return
        self._btn_salvar.setEnabled(False)  # trava contra duplo envio (F10 + clique)
        self._status.setText("Salvando…")
        rodar(self._executar_salvar, on_ok=self._salvo, on_erro=self._erro_salvar)

    def _salvo(self, dado: dict) -> None:
        self._preencher(dado or {})
        self._btn_salvar.setEnabled(not self._modo_leitura)
        self._status.setText("Alterações salvas.")

    def _erro_salvar(self, msg: str) -> None:
        self._btn_salvar.setEnabled(not self._modo_leitura)
        self._status.setText("")
        QMessageBox.critical(self, "Não foi possível salvar", msg)

    # ----------------------------------------------------------------- hooks

    def _secoes(self):
        raise NotImplementedError

    def _buscar(self) -> dict:
        return self._api.empresa()

    def _executar_salvar(self) -> dict:
        return self._api.atualizar_empresa(self._payload())

    def _preencher(self, dado: dict) -> None:
        raise NotImplementedError

    def _payload(self) -> dict:
        raise NotImplementedError

    def _validar(self):
        return None


# ============================================================ dados da empresa


class PaginaEmpresa(PaginaFicha):
    ROTULO_PAGINA = "Dados da Empresa"

    def _secoes(self):
        self._razao = CampoTexto("Razão social", maximo=200).obrigatorio()
        self._fantasia = CampoTexto("Nome fantasia", maximo=120)
        self._cnpj = CampoTexto("CNPJ", maximo=14)
        self._ie = CampoTexto("Inscrição estadual", maximo=20)
        self._im = CampoTexto("Inscrição municipal", maximo=20)
        self._regime = CampoTexto("Regime tributário", maximo=60)
        self._cnae = CampoTexto("CNAE fiscal", maximo=10)
        self._ambiente = CampoCombo(
            "Ambiente fiscal", [("h", "Homologação"), ("p", "Produção")]
        )
        self._logradouro = CampoTexto("Logradouro", maximo=160)
        self._numero = CampoTexto("Número", maximo=12)
        self._complemento = CampoTexto("Complemento", maximo=80)
        self._bairro = CampoTexto("Bairro", maximo=80)
        self._cidade = CampoTexto("Cidade", maximo=80)
        self._uf = CampoTexto("UF", maximo=2)
        self._cep = CampoTexto("CEP", maximo=8)
        self._telefone = CampoTexto("Telefone", maximo=20)
        self._email = CampoTexto("E-mail", maximo=120)
        self._site = CampoTexto("Site", maximo=160)
        return [
            (
                "Identificação",
                [
                    self._razao,
                    self._fantasia,
                    self._cnpj,
                    self._ie,
                    self._im,
                    self._regime,
                    self._cnae,
                    self._ambiente,
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
            ("Contato", [self._telefone, self._email, self._site]),
        ]

    def _preencher(self, dado: dict) -> None:
        self._razao.definir(dado.get("razao_social"))
        self._fantasia.definir(dado.get("nome_fantasia"))
        self._cnpj.definir(dado.get("cnpj"))
        self._ie.definir(dado.get("inscricao_estadual"))
        self._im.definir(dado.get("inscricao_municipal"))
        self._regime.definir(dado.get("regime_tributario"))
        self._cnae.definir(dado.get("cnae_fiscal"))
        self._ambiente.definir(dado.get("ambiente_fiscal") or "h")
        self._logradouro.definir(dado.get("logradouro"))
        self._numero.definir(dado.get("numero"))
        self._complemento.definir(dado.get("complemento"))
        self._bairro.definir(dado.get("bairro"))
        self._cidade.definir(dado.get("cidade"))
        self._uf.definir(dado.get("uf"))
        self._cep.definir(dado.get("cep"))
        self._telefone.definir(dado.get("telefone"))
        self._email.definir(dado.get("email"))
        self._site.definir(dado.get("website"))

    def _validar(self):
        if not self._razao.valido():
            return ("Informe a razão social.", self._razao)
        cnpj = self._cnpj.valor()
        if cnpj and len(cnpj) != 14:
            return ("O CNPJ deve ter 14 dígitos.", self._cnpj)
        return None

    def _payload(self) -> dict:
        return {
            "razao_social": self._razao.valor(),
            "nome_fantasia": limpo(self._fantasia.valor()),
            "cnpj": limpo(self._cnpj.valor()),
            "inscricao_estadual": limpo(self._ie.valor()),
            "inscricao_municipal": limpo(self._im.valor()),
            "regime_tributario": limpo(self._regime.valor()),
            "cnae_fiscal": limpo(self._cnae.valor()),
            "ambiente_fiscal": self._ambiente.valor() or "h",
            "logradouro": limpo(self._logradouro.valor()),
            "numero": limpo(self._numero.valor()),
            "complemento": limpo(self._complemento.valor()),
            "bairro": limpo(self._bairro.valor()),
            "cidade": limpo(self._cidade.valor()),
            "uf": limpo(self._uf.valor()),
            "cep": limpo(self._cep.valor()),
            "telefone": limpo(self._telefone.valor()),
            "email": limpo(self._email.valor()),
            "website": limpo(self._site.valor()),
        }


# =============================================================== personalização


class PaginaPersonalizacao(PaginaFicha):
    ROTULO_PAGINA = "Personalização"

    def _secoes(self):
        self._logotipo = CampoArquivo("Logotipo")
        self._fundo = CampoArquivo("Fundo de tela")
        self._matricial = CampoTexto("Impressora matricial", maximo=160)
        self._cupom = CampoTexto("Impressora de cupom", maximo=160)
        return [
            ("Marca", [self._logotipo, self._fundo]),
            ("Impressão", [self._matricial, self._cupom]),
        ]

    def _preencher(self, dado: dict) -> None:
        self._logotipo.definir(dado.get("logotipo_path"))
        self._fundo.definir(dado.get("fundo_tela_path"))
        self._matricial.definir(dado.get("impressora_matricial"))
        self._cupom.definir(dado.get("impressora_cupom"))

    def _payload(self) -> dict:
        # Atualização parcial: toca só as chaves de personalização.
        return {
            "logotipo_path": limpo(self._logotipo.valor()),
            "fundo_tela_path": limpo(self._fundo.valor()),
            "impressora_matricial": limpo(self._matricial.valor()),
            "impressora_cupom": limpo(self._cupom.valor()),
        }


# =========================================================== reajuste em bloco


class PaginaReajuste(QWidget):
    """Reajuste de Preços em Bloco (§2.6): prévia obrigatória + senha ao aplicar."""

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._previa: dict | None = None
        self._categorias: list[tuple[int, str]] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(10)
        raiz.addWidget(self._barra_titulo())

        if self._modo_leitura:
            aviso = QLabel(
                "Modo leitura: a simulação e a aplicação do reajuste estão bloqueadas."
            )
            aviso.setObjectName("bannerLeitura")
            raiz.addWidget(aviso)

        raiz.addWidget(self._painel_parametros())

        self._resumo = QLabel("Clique em Simular para ver a prévia do reajuste.")
        self._resumo.setObjectName("subtitulo")
        self._resumo.setWordWrap(True)
        raiz.addWidget(self._resumo)

        self._tabela = TabelaDensa(
            ["codigo", "nome", "preco_antes", "preco_depois", "variacao"],
            ["Código", "Produto", "Antes", "Depois", "Variação"],
            [2, 6, 2, 2, 2],
        )
        self._tabela.formata = self._formatar_previa
        self._tabela.estado_vazio("Nenhuma prévia gerada. Ajuste os critérios e clique em Simular (F8).")
        raiz.addWidget(self._tabela, 1)

        raiz.addWidget(self._painel_historico())

        QShortcut(QKeySequence("F8"), self, self._simular)
        QShortcut(QKeySequence("F9"), self, self._aplicar)

        self._aplicar_modo_leitura()
        self._criterio_mudou()
        self._carregar_categorias()
        self._carregar_historico()

    # ------------------------------------------------------------ construção

    def _barra_titulo(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        titulo = ElideLabel("Reajuste de Preços em Bloco")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo, 1)
        linha.addWidget(badge("AUDITADO", "primary"))
        return caixa

    def _painel_parametros(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(10)
        col.addWidget(rotulo_secao("Parâmetros do reajuste"))

        self._criterio = CampoCombo(
            "Critério",
            [("todos", "Todos os produtos"), ("categoria", "Por categoria")],
        )
        self._categoria = CampoCombo("Categoria", [])
        self._tipo = CampoCombo(
            "Tipo",
            [("percentual", "Percentual (%)"), ("valor_fixo", "Valor fixo (R$)")],
        )
        self._valor = CampoValor("Valor", prefixo="")
        self._valor.edicao.setPlaceholderText("Ex.: 10 (para 10%)")
        self._criterio.widget.currentIndexChanged.connect(self._criterio_mudou)
        self._tipo.widget.currentIndexChanged.connect(self._tipo_mudou)

        grade = grade_campos()
        dispor_campos(grade, [self._criterio, self._categoria, self._tipo, self._valor])
        col.addLayout(grade)

        botoes = QHBoxLayout()
        botoes.setContentsMargins(0, 0, 0, 0)
        botoes.addStretch(1)
        simular, self._btn_simular = botao_com_atalho("Simular", "F8")
        aplicar, self._btn_aplicar = botao_com_atalho("Aplicar reajuste", "F9", "primary")
        self._btn_simular.clicked.connect(self._simular)
        self._btn_aplicar.clicked.connect(self._aplicar)
        botoes.addWidget(simular)
        botoes.addWidget(aplicar)
        col.addLayout(botoes)
        return card

    def _painel_historico(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        col = QVBoxLayout(card)
        col.setContentsMargins(16, 12, 16, 12)
        col.setSpacing(6)
        col.addWidget(rotulo_secao("Últimos reajustes (trilha de auditoria)"))
        self._historico = QLabel("Carregando…")
        self._historico.setObjectName("subtitulo")
        self._historico.setWordWrap(True)
        col.addWidget(self._historico)
        return card

    # ---------------------------------------------------------------- estado

    def _aplicar_modo_leitura(self) -> None:
        self._btn_simular.setEnabled(not self._modo_leitura)
        self._btn_aplicar.setEnabled(False)
        self._valor.habilitar(not self._modo_leitura)
        self._criterio.habilitar(not self._modo_leitura)
        self._tipo.habilitar(not self._modo_leitura)
        self._categoria.habilitar(
            not self._modo_leitura and self._criterio.valor() == "categoria"
        )

    def _criterio_mudou(self) -> None:
        self._categoria.habilitar(
            not self._modo_leitura and self._criterio.valor() == "categoria"
        )

    def _tipo_mudou(self) -> None:
        if self._tipo.valor() == "percentual":
            self._valor.edicao.setPlaceholderText("Ex.: 10 (para 10%)")
        else:
            self._valor.edicao.setPlaceholderText("Ex.: 5,00 (por produto)")

    # ------------------------------------------------------------ categorias

    def _carregar_categorias(self) -> None:
        catalogos.carregar(
            "categorias",
            lambda: self._api.listar("categorias", limit=1000),
            on_ok=self._categorias_recebidas,
        )

    def _categorias_recebidas(self, saida: dict) -> None:
        dados = saida.get("data", [])
        self._categorias = [(r["id"], r["nome"]) for r in dados]
        self._categoria.alterar_opcoes(self._categorias)

    # --------------------------------------------------------------- payload

    def _payload(self) -> dict:
        valor = self._valor.valor()
        return {
            "criterio": self._criterio.valor(),
            "categoria_id": (
                self._categoria.valor() if self._criterio.valor() == "categoria" else None
            ),
            "tipo_reajuste": self._tipo.valor(),
            "valor": str(valor) if valor is not None else "0",
        }

    def _validar(self) -> bool:
        valor = self._valor.valor()
        if valor is None or valor <= 0:
            QMessageBox.warning(self, "Reajuste", "Informe um valor de reajuste maior que zero.")
            self._valor.edicao.setFocus()
            return False
        if self._criterio.valor() == "categoria" and self._categoria.valor() is None:
            QMessageBox.warning(self, "Reajuste", "Selecione a categoria do reajuste.")
            self._categoria.widget.setFocus()
            return False
        return True

    # --------------------------------------------------------------- simular

    def _simular(self) -> None:
        if self._modo_leitura or not self._validar():
            return
        self._btn_simular.setEnabled(False)
        self._btn_aplicar.setEnabled(False)
        self._resumo.setText("Simulando…")
        rodar(
            lambda: self._api.simular_reajuste(self._payload()),
            on_ok=self._previa_recebida,
            on_erro=self._erro,
        )

    def _previa_recebida(self, dados: dict) -> None:
        self._previa = dados
        self._tabela.preencher(dados.get("itens", []))
        afetados = dados.get("afetados", 0)
        bloqueados = dados.get("bloqueados", 0)
        self._resumo.setText(
            f"Prévia: {afetados} produto(s) elegível(is) · "
            f"{bloqueados} bloqueado(s) para reajuste (protegidos)."
        )
        self._btn_simular.setEnabled(not self._modo_leitura)
        self._btn_aplicar.setEnabled(afetados > 0 and not self._modo_leitura)

    # --------------------------------------------------------------- aplicar

    def _aplicar(self) -> None:
        if self._modo_leitura or self._previa is None or not self._previa.get("itens"):
            QMessageBox.warning(
                self, "Reajuste", "Gere a simulação (F8) antes de aplicar o reajuste."
            )
            return
        senha, ok = QInputDialog.getText(
            self,
            "Confirmar reajuste",
            "Senha do administrador:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not senha:
            return
        self._btn_aplicar.setEnabled(False)
        self._resumo.setText("Aplicando…")
        payload = {**self._payload(), "senha": senha}
        rodar(
            lambda: self._api.aplicar_reajuste(payload),
            on_ok=self._aplicado,
            on_erro=self._erro,
        )

    def _aplicado(self, dados: dict) -> None:
        afetados = dados.get("afetados", 0)
        self._resumo.setText(f"Reajuste aplicado em {afetados} produto(s).")
        self._previa = None
        self._tabela.limpar()
        self._tabela.estado_vazio("Reajuste aplicado. Gere uma nova prévia para reajustar novamente.")
        self._btn_simular.setEnabled(not self._modo_leitura)
        self._btn_aplicar.setEnabled(False)
        self._carregar_historico()
        QMessageBox.information(
            self, "Reajuste aplicado", f"{afetados} produto(s) reajustado(s) com sucesso."
        )

    def _erro(self, msg: str) -> None:
        self._resumo.setText("")
        self._btn_simular.setEnabled(not self._modo_leitura)
        self._btn_aplicar.setEnabled(
            bool(self._previa and self._previa.get("itens")) and not self._modo_leitura
        )
        QMessageBox.critical(self, "Reajuste", msg)

    # -------------------------------------------------------------- histórico

    def _carregar_historico(self) -> None:
        rodar(
            lambda: self._api.reajuste_historico(limit=5),
            on_ok=self._historico_recebido,
            on_erro=lambda _msg: self._historico.setText("Não foi possível carregar o histórico."),
        )

    def _historico_recebido(self, saida: dict) -> None:
        linhas = saida.get("data", [])
        if not linhas:
            self._historico.setText("Nenhum reajuste registrado ainda.")
            return
        partes = []
        for registro in linhas:
            if registro.get("tipo_reajuste") == "percentual":
                magnitude = f"{formatar_percentual(registro.get('valor_reajuste'))}%"
            else:
                magnitude = formatar_moeda(registro.get("valor_reajuste"))
            partes.append(
                f"{formatar_data_hora(registro.get('executado_em'))} · {magnitude} · "
                f"{registro.get('itens_afetados')} item(ns) · {registro.get('criterio')}"
            )
        self._historico.setText("\n".join(partes))

    # -------------------------------------------------------------- formatação

    def _formatar_previa(self, dado: dict, chave: str) -> str:
        if chave in ("preco_antes", "preco_depois"):
            return formatar_moeda(dado.get(chave))
        if chave == "variacao":
            return self._variacao(dado.get("preco_antes"), dado.get("preco_depois"))
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

    @staticmethod
    def _variacao(antes, depois) -> str:
        try:
            antes_dec = Decimal(str(antes))
            depois_dec = Decimal(str(depois))
        except (InvalidOperation, TypeError, ValueError):
            return ""
        if antes_dec == 0:
            return "—"
        pct = (depois_dec - antes_dec) / antes_dec * 100
        sinal = "+" if pct > 0 else ""
        return f"{sinal}{pct:.1f}%".replace(".", ",")


# ============================================================== usuários níveis


class PaginaUsuarios(PaginaCrud):
    """Gestão de usuários e níveis de acesso (`/v1/usuarios`, exclusivo admin)."""

    ENTIDADE = "usuarios"
    ROTULO_PAGINA = "Usuários e Níveis de Acesso"
    ROTULO_NOVO = "Novo Usuário"
    GRUPO_LISTA = "USUÁRIOS"
    LUGAR_BUSCA = "Buscar por nome, login ou e-mail..."
    CAMPO_NOME = "nome"
    CHAVES = ["id", "nome", "login", "nivel_acesso", "email", "ativo"]
    COLUNAS = ["Nº", "Nome", "Login", "Nível", "E-mail", "Ativo"]
    PESOS = [1, 4, 3, 2, 4, 1]
    CHAVE_FILTRO = "nivel_acesso"
    FILTROS = [("", "Todos"), ("admin", "Administrador"), ("gerente", "Gerente"), ("operador", "Operador"), ("caixa", "Caixa")]
    FILTRO_LOCAL = True  # /v1/usuarios não filtra por nível no servidor

    def _secoes(self):
        self._nome = CampoTexto("Nome", maximo=120).obrigatorio()
        self._login = CampoTexto("Login", maximo=60)
        self._email = CampoTexto("E-mail", maximo=120)
        self._nivel = CampoCombo("Nível de acesso", _NIVEIS)
        self._ativo = CampoCheck("Ativo")
        self._senha = CampoTexto("Senha", maximo=128)
        return [
            ("Identificação", [self._nome, self._email]),
            ("Acesso", [self._login, self._nivel, self._ativo, self._senha]),
        ]

    def _preencher_campos(self, dado: dict) -> None:
        self._nome.definir(dado.get("nome"))
        self._login.definir(dado.get("login"))
        self._login.habilitar(False)  # login é imutável depois de criado
        self._email.definir(dado.get("email"))
        self._nivel.definir(dado.get("nivel_acesso"))
        self._ativo.definir(dado.get("ativo"))
        self._senha.definir("")
        self._senha.widget.setPlaceholderText("Deixe em branco para manter a senha atual")

    def _padroes_do_form(self) -> None:
        self._nivel.definir("operador")
        self._ativo.definir(True)
        self._login.habilitar(not self._modo_leitura)
        self._senha.widget.setPlaceholderText("Mínimo de 8 caracteres")

    def _validar(self):
        if not self._nome.valido():
            return ("Informe o nome do usuário.", self._nome)
        senha = self._senha.valor()
        if self._editando_id is None:
            if not self._login.valor():
                return ("Informe o login de acesso.", self._login)
            if len(senha) < 8:
                return ("A senha precisa ter ao menos 8 caracteres.", self._senha)
        elif senha and len(senha) < 8:
            return ("A senha precisa ter ao menos 8 caracteres.", self._senha)
        return None

    def _payload(self) -> dict:
        dados = {
            "nome": self._nome.valor(),
            "email": limpo(self._email.valor()),
            "nivel_acesso": self._nivel.valor(),
            "ativo": self._ativo.valor(),
        }
        senha = self._senha.valor()
        if self._editando_id is None:
            dados["login"] = self._login.valor()
            dados["senha"] = senha
        elif senha:
            dados["senha"] = senha
        return dados

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "nivel_acesso":
            return _NIVEL_ROTULO.get(dado.get(chave), str(dado.get(chave) or ""))
        if chave == "ativo":
            return "Sim" if dado.get(chave) else "Não"
        return super()._formatar_texto(dado, chave)


# ==================================================================== host


class PaginaConfiguracoes(QWidget):
    """Menu "Configurações": hospeda as sub-abas conforme o perfil do usuário."""

    def __init__(self, api: Api, modo_leitura: bool = False, nivel: str | None = None) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        candidatas = [
            ("dados_empresa", "Dados da Empresa", PaginaEmpresa),
            ("personalizacao", "Personalização", PaginaPersonalizacao),
            ("reajuste_bloco", "Reajuste de Preços", PaginaReajuste),
            ("usuarios", "Usuários e Níveis", PaginaUsuarios),
        ]
        # RBAC não hierárquico: o item interno é visível só ao admin.
        self._abas = [
            (rotulo, classe)
            for item_id, rotulo, classe in candidatas
            if nivel is None or pode_abrir(nivel, item_id)
        ]
        self._atual: QWidget | None = None

        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._barra())
        self._corpo = QWidget()
        self._corpo_layout = QVBoxLayout(self._corpo)
        self._corpo_layout.setContentsMargins(0, 0, 0, 0)
        col.addWidget(self._corpo, 1)

        if self._abas:
            self._trocar(0)
        else:
            restrito = QLabel("Acesso restrito a administradores.")
            restrito.setObjectName("subtitulo")
            self._corpo_layout.addWidget(restrito)

    def _barra(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 16, 20, 0)
        linha.setSpacing(8)
        titulo = ElideLabel("Configurações")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo)
        linha.addStretch(1)
        self._botoes = []
        for indice, (rotulo, _classe) in enumerate(self._abas):
            botao = QPushButton(rotulo)
            botao.setObjectName("chaveRapida")
            botao.setCheckable(True)
            botao.setChecked(indice == 0)
            botao.clicked.connect(lambda _=False, i=indice: self._trocar(i))
            self._botoes.append(botao)
            linha.addWidget(botao)
        return caixa

    def _trocar(self, indice: int) -> None:
        _rotulo, classe = self._abas[indice]
        pagina = classe(self._api, modo_leitura=self._modo_leitura)
        if self._atual is not None:
            self._corpo_layout.removeWidget(self._atual)
            self._atual.deleteLater()
        self._corpo_layout.addWidget(pagina)
        self._atual = pagina
        for i, botao in enumerate(self._botoes):
            botao.setChecked(i == indice)
