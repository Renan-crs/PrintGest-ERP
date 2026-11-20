"""Configurações > Integrações (PRD v3.3 §3.6).

Tela Admin-only para cadastrar apps de terceiros (emissor de nota fiscal,
email, pagamento, genérica): URL base, cabeçalho de autenticação e — o ponto
central — **API key/token e certificado**, que são enviados ao servidor e
guardados no **cofre do SO (DPAPI)**, nunca em texto no banco, log ou backup.

A UI NUNCA recebe o segredo de volta: exibe apenas máscara (`••••1234`) e o
botão de teste de conexão. Segue o padrão de abas de `PaginaConfiguracoes`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import printgest.core.tarefas as tarefas
from printgest.core.api import Api
from printgest.ui.formulario import (
    CampoCheck,
    CampoCombo,
    CampoTexto,
    em_volta,
    grade_campos,
    rotulo_secao,
)
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import (
    ElideLabel,
    aplicar_estilo,
    estado_atencao,
    estado_muted,
    estado_sucesso,
    estado_primario,
    estado_secundario,
)

TIPOS = [
    ("fiscal", "Emissor de Nota Fiscal (NF-e / NFC-e / NFS-e)"),
    ("email", "Email / SMTP"),
    ("pagamento", "Gateway de Pagamento"),
    ("generica", "API genérica"),
]
CHAVES = ["tipo", "nome", "provedor", "base_url", "status", "credencial_mascara"]
COLUNAS = ["Tipo", "Nome", "Provedor", "URL base", "Situação", "Credencial"]
PESOS = [2, 4, 3, 6, 2, 2]


class PaginaIntegracoes(QWidget):
    """Lista + formulário de integrações de terceiros."""

    ROTULO_PAGINA = "Integrações"

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._editando_id: int | None = None
        self._itens: list[dict] = []
        self._montar()
        self._carregar()

    # ------------------------------------------------------------------ UI

    def _montar(self) -> None:
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        titulo = ElideLabel(self.ROTULO_PAGINA)
        titulo.setObjectName("titulo")
        col.addWidget(titulo)

        aviso = QLabel(
            "Credenciais de API e certificados são guardados no cofre do SO "
            "(DPAPI) e nunca exibidos novamente — apenas uma máscara."
        )
        aviso.setObjectName("bannerLeitura")
        aviso.setWordWrap(True)
        col.addWidget(aviso)

        self._tabela = TabelaDensa(CHAVES, COLUNAS, PESOS)
        self._tabela.formata = self._formatar_texto
        self._tabela.itemSelectionChanged.connect(self._selecionado)
        cab = self._tabela.horizontalHeader()
        cab.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        # Formulário longo: tabela limitada e formulário rolável (1024×768).
        self._tabela.setMinimumHeight(140)
        self._tabela.setMaximumHeight(240)
        col.addWidget(self._tabela, 0)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._form = self._montar_form()
        rolagem.setWidget(self._form)
        col.addWidget(rolagem, 1)

    def _montar_form(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        self._lbl_form = QLabel("Nova integração")
        self._lbl_form.setObjectName("labelForm")
        lay.addWidget(self._lbl_form)

        self._tipo = CampoCombo("Tipo", TIPOS)
        self._nome = CampoTexto("Nome", maximo=120).obrigatorio()
        self._provedor = CampoTexto("Provedor", maximo=120)
        self._base_url = CampoTexto("URL base da API", maximo=500)
        self._base_url.widget.setPlaceholderText("https://api.provedor.com/v1")
        self._auth_header = CampoTexto("Cabeçalho de autenticação", valor="Authorization")
        self._auth_prefix = CampoTexto("Prefixo do token", valor="Bearer ")
        self._ambiente = CampoCombo(
            "Ambiente", [("homologacao", "Homologação"), ("producao", "Produção")]
        )
        self._ativo = CampoCheck("Integração ativa")
        self._ativo.definir(True)

        g1 = grade_campos()
        g1.addWidget(em_volta(self._tipo), 0, 0)
        g1.addWidget(em_volta(self._nome), 0, 1)
        g1.addWidget(em_volta(self._provedor), 1, 0)
        g1.addWidget(em_volta(self._base_url), 1, 1)
        lay.addWidget(rotulo_secao("Serviço"))
        lay.addLayout(g1)

        g2 = grade_campos()
        g2.addWidget(em_volta(self._auth_header), 0, 0)
        g2.addWidget(em_volta(self._auth_prefix), 0, 1)
        g2.addWidget(em_volta(self._ambiente), 1, 0)
        g2.addWidget(em_volta(self._ativo), 1, 1)
        lay.addWidget(rotulo_secao("Autenticação"))
        lay.addLayout(g2)

        # Campo de segredo: NUNCA é preenchido na carga; writeOnly.
        self._credencial = CampoTexto("API key / Token", maximo=4000)
        self._credencial.widget.setEchoMode(
            self._credencial.widget.EchoMode.Password
        )
        self._credencial.widget.setPlaceholderText(
            "Deixe em branco para manter a credencial atual"
        )
        self._certificado = CampoTexto("Certificado de API (PEM/Base64)", maximo=20000)
        self._certificado.widget.setPlaceholderText(
            "Conteúdo do certificado — nunca é exibido depois de salvo"
        )
        self._lbl_mascaras = QLabel("")
        estado_muted(self._lbl_mascaras)
        lay.addWidget(rotulo_secao("Credenciais (cofre do SO)"))
        lay.addWidget(em_volta(self._credencial))
        lay.addWidget(em_volta(self._certificado))
        lay.addWidget(self._lbl_mascaras)

        linha = QHBoxLayout()
        linha.addStretch(1)
        self._btn_testar = QPushButton("Testar conexão")
        estado_secundario(self._btn_testar)
        self._btn_testar.clicked.connect(self._testar)
        self._btn_limpar = QPushButton("Limpar")
        estado_secundario(self._btn_limpar)
        self._btn_limpar.clicked.connect(self._limpar)
        self._btn_salvar = QPushButton("Salvar")
        estado_primario(self._btn_salvar)
        self._btn_salvar.clicked.connect(self._salvar)
        for b in (self._btn_testar, self._btn_limpar, self._btn_salvar):
            linha.addWidget(b)
        lay.addLayout(linha)
        return card

    # ------------------------------------------------------------- carregar

    def _carregar(self) -> None:
        def ok(saida: dict) -> None:
            self._itens = saida.get("data", []) if isinstance(saida, dict) else []
            self._tabela.preencher(self._itens)

        def erro(msg: str, status: int | None = None) -> None:
            estado_atencao(self._lbl_mascaras)
            titulo = (
                "Sessão encerrada" if status == 401
                else "Modo leitura" if status == 423
                else "Integrações"
            )
            self._lbl_mascaras.setText(f"{titulo}: {msg}")

        tarefas.rodar(self._api.listar_integracoes, ok, erro)

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "tipo":
            return dict(TIPOS).get(dado.get("tipo"), str(dado.get("tipo", "")))
        if chave == "base_url":
            return str(dado.get("base_url") or "—")
        if chave == "credencial_mascara":
            return dado.get("credencial_mascara") or "—"
        if chave == "status":
            if not dado.get("ativo"):
                return "Inativa"
            if dado.get("ultimo_teste_ok") is True:
                return "OK"
            if dado.get("ultimo_teste_ok") is False:
                return "Falha no teste"
            return "Ativa"
        return str(dado.get(chave) or "")

    def _selecionado(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            return
        self._editando_id = dado.get("id")
        self._lbl_form.setText(f"Editando: {dado.get('nome')}")
        self._tipo.definir(dado.get("tipo"))
        self._nome.definir(dado.get("nome"))
        self._provedor.definir(dado.get("provedor"))
        self._base_url.definir(dado.get("base_url"))
        self._auth_header.definir(dado.get("auth_header") or "Authorization")
        self._auth_prefix.definir(dado.get("auth_prefix") or "Bearer ")
        self._ambiente.definir(dado.get("ambiente") or "homologacao")
        self._ativo.definir(bool(dado.get("ativo")))
        # NUNCA preenche o campo de segredo com o valor実 — só máscara informativa.
        self._credencial.definir(None)
        self._certificado.definir(None)
        partes = []
        if dado.get("credencial_mascara"):
            partes.append(f"API key: {dado['credencial_mascara']}")
        if dado.get("certificado_mascara"):
            partes.append(f"Certificado: {dado['certificado_mascara']}")
        self._lbl_mascaras.setText(
            "Armazenado no cofre: " + " · ".join(partes)
            if partes
            else "Nenhuma credencial cadastrada."
        )
        estado_muted(self._lbl_mascaras)
        self._aplicar_modo_leitura()

    # -------------------------------------------------------------- ações

    def _payload(self) -> dict:
        p = {
            "tipo": self._tipo.valor(),
            "nome": (self._nome.valor() or "").strip(),
            "provedor": (self._provedor.valor() or "").strip() or None,
            "base_url": (self._base_url.valor() or "").strip() or None,
            "auth_header": (self._auth_header.valor() or "Authorization").strip(),
            "auth_prefix": self._auth_prefix.valor() or "",
            "ambiente": self._ambiente.valor() or "homologacao",
            "ativo": self._ativo.valor(),
        }
        cred = self._credencial.valor()
        cert = self._certificado.valor()
        if cred:
            p["credencial"] = cred
        if cert:
            p["certificado"] = cert
        return p

    def _validar(self) -> str | None:
        if not (self._nome.valor() or "").strip():
            return "Informe o nome da integração."
        url = (self._base_url.valor() or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            return "A URL base deve começar com http:// ou https://."
        return None

    def _salvar(self) -> None:
        if self._modo_leitura:
            return
        problema = self._validar()
        if problema:
            QMessageBox.warning(self, "Integrações", problema)
            return
        payload = self._payload()
        self._btn_salvar.setEnabled(False)

        def ok(_resposta) -> None:
            self._btn_salvar.setEnabled(True)
            self._limpar()
            self._carregar()
            QMessageBox.information(
                self,
                "Integrações",
                "Integração salva. Credenciais guardadas no cofre do SO.",
            )

        def erro(msg: str, status: int | None = None) -> None:
            self._btn_salvar.setEnabled(True)
            titulo = (
                "Sessão encerrada" if status == 401
                else "Modo leitura" if status == 423
                else "Integrações"
            )
            QMessageBox.warning(self, titulo, msg)

        if self._editando_id:
            acao = lambda: self._api.atualizar_integracao(self._editando_id, payload)
        else:
            acao = lambda: self._api.criar_integracao(payload)
        tarefas.rodar(acao, ok, erro)

    def _testar(self) -> None:
        if self._editando_id is None:
            QMessageBox.information(self, "Integrações", "Salve a integração antes de testar.")
            return
        self._btn_testar.setEnabled(False)

        def ok(saida: dict) -> None:
            self._btn_testar.setEnabled(True)
            dado = saida.get("data", saida) if isinstance(saida, dict) else {}
            if dado.get("ok"):
                estado_sucesso(self._lbl_mascaras)
                self._lbl_mascaras.setText(f"Conexão OK (HTTP {dado.get('status_http')}).")
            else:
                estado_atencao(self._lbl_mascaras)
                self._lbl_mascaras.setText(f"Falha: {dado.get('mensagem')}")

        def erro(msg: str, status: int | None = None) -> None:
            self._btn_testar.setEnabled(True)
            titulo = (
                "Sessão encerrada" if status == 401
                else "Modo leitura" if status == 423
                else "Teste de conexão"
            )
            QMessageBox.warning(self, titulo, msg)

        tarefas.rodar(
            lambda: self._api.testar_integracao(self._editando_id), ok, erro
        )

    def _limpar(self) -> None:
        self._editando_id = None
        self._lbl_form.setText("Nova integração")
        self._tipo.definir("fiscal")
        self._nome.definir(None)
        self._provedor.definir(None)
        self._base_url.definir(None)
        self._auth_header.definir("Authorization")
        self._auth_prefix.definir("Bearer ")
        self._ambiente.definir("homologacao")
        self._ativo.definir(True)
        self._credencial.definir(None)
        self._certificado.definir(None)
        self._lbl_mascaras.setText("")
        self._aplicar_modo_leitura()

    def _aplicar_modo_leitura(self) -> None:
        ligado = not self._modo_leitura
        self._btn_salvar.setEnabled(ligado)
        self._btn_testar.setEnabled(ligado)
        for campo in (
            self._tipo,
            self._nome,
            self._provedor,
            self._base_url,
            self._auth_header,
            self._auth_prefix,
            self._ambiente,
            self._ativo,
            self._credencial,
            self._certificado,
        ):
            campo.habilitar(ligado)
