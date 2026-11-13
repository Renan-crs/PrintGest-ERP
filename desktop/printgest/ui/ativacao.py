"""Tela 1.2 — Ativação de Licença (primeira execução, modo Servidor).

Coluna única centralizada (revisão UI/UX out/2026 — docs/revisao_tela_ativacao.md):
- três ações com rótulo visível, altura >= 40 px e atalho no próprio texto;
- formulário dinâmico pelo contrato ativo (PRD §5.1): B = CNPJ + código,
  C = chave de produto XXXX-XXXX-XXXX-XXXX;
- validação em linha (dígito verificador do CNPJ) e erro junto do campo;
- progresso não interativo "Passo X de 3" (D1); ao ativar, resumo + Entrar;
- PT-BR sem jargão na superfície (C2/C4); detalhes técnicos recolhidos e
  diagnóstico do servidor local automático (D3).

Regras preservadas (PRD §4/§5.1): F10 ativa, Esc sai (com confirmação), timeout
de ativação >= 90 s no cliente (`Api.TIMEOUT_ATIVACAO_SEGUNDOS`) e nenhuma
revogação por indisponibilidade — tratada pelo servidor (503 nunca revoga).
"""

from __future__ import annotations

import re

from PySide6.QtCore import QAbstractAnimation, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.widgets import (
    EtiquetaQuebra,
    aplicar_estilo,
    estado_primario,
    estado_secundario,
    estado_sucesso,
    estado_erro,
    estado_muted,
    formatar_datahora,
    marca_printgest,
)

_FORMATO_CHAVE = re.compile(r"^[0-9A-F]{4}(-[0-9A-F]{4}){3}$")

# Passos (D1): indicador não interativo — texto + pontos, sem cara de botão.
_PASSOS_B = ["Dados da licença", "Validação online", "Sistema liberado"]
_PASSOS_C = ["Chave de produto", "Validação online", "Sistema liberado"]

# Espaçamentos da escala 4/8/16/24 (B1): rótulo→campo 4, entre grupos 24.
_GAP_ROTULO_CAMPO = 4
_GAP_ENTRE_GRUPOS = 24


class AtivacaoWindow(QMainWindow):
    """Tela de ativação exibida quando ainda não existe licença associada."""

    ativada = Signal()
    saida = Signal()

    def __init__(
        self,
        api: Api,
        token: str | None = None,
        contrato: str = "c",
        situacao: dict | None = None,
    ) -> None:
        super().__init__()
        self._api = api
        self._token = token
        self._contrato_b = (contrato or "c").strip().lower() == "b"
        # Inquilino instalado (CNPJ informado no assistente de instalação):
        # pré-preenche o campo e evita ativar licença de outra gráfica.
        self._tenant = situacao or {}
        self._passo = 1
        self._validando = False
        self._tentativa = 0
        self._cliente_ativacao: "httpx.Client | None" = None  # só p/ abortar (D2)
        self._animacao_detalhes = None
        self._animacoes = self._animacoes_habilitadas()
        self.setWindowTitle("PrintGest ERP — Ativação de licença")
        self.setMinimumSize(960, 640)

        base = QWidget()
        externa = QVBoxLayout(base)
        externa.setContentsMargins(48, 40, 48, 24)
        externa.addStretch(3)

        # Coluna de largura fixa, centralizada como BLOCO: itens sem alinhamento
        # por-item para o heightForWidth dos labels com quebra funcionar (A2).
        bloco = QWidget()
        bloco.setMaximumWidth(560)
        coluna = QVBoxLayout(bloco)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(8)

        coluna.addWidget(self._marca(), 0, Qt.AlignmentFlag.AlignHCenter)
        coluna.addSpacing(8)
        coluna.addWidget(self._titulo())
        coluna.addWidget(self._subtitulo())
        coluna.addWidget(self._cabecalho_passo())
        coluna.addWidget(self._cartao())
        coluna.addWidget(self._painel_detalhes())
        coluna.addLayout(self._rodape())
        coluna.addSpacing(4)
        coluna.addWidget(self._linha_tolerancia())
        externa.addWidget(bloco, 0, Qt.AlignmentFlag.AlignHCenter)
        externa.addStretch(4)

        self.setCentralWidget(base)

        # Teclado e foco (A6/D5/F1).
        QShortcut(QKeySequence(Qt.Key.Key_F10), self, self._ativar)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._solicitar_saida)
        self._definir_ordem_de_foco()
        if self._contrato_b:
            self._campo_cnpj.setFocus()
        else:
            self._campo_chave.setFocus()

        # Diagnóstico do servidor local já ao abrir (D3).
        self._testar()

    # ------------------------------------------------------------ cabeçalho

    @staticmethod
    def _marca() -> QLabel:
        return marca_printgest()

    @staticmethod
    def _titulo() -> QLabel:
        lbl = QLabel("Ativar o PrintGest")
        lbl.setObjectName("tituloAtivacao")
        return lbl

    def _subtitulo(self) -> QLabel:
        lbl = EtiquetaQuebra(
            "Informe os dados da contratação para liberar este computador."
        )
        lbl.setObjectName("subtitulo")
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        return lbl

    def _cabecalho_passo(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 6, 0, 0)
        linha.setSpacing(10)
        linha.addStretch(1)  # texto + pontos centralizados no bloco
        self._passo_texto = QLabel()
        self._passo_texto.setObjectName("subtitulo")
        linha.addWidget(self._passo_texto)
        self._dots: list[QLabel] = []
        for _ in range(3):
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setProperty("passo", "pendente")
            dot.setAccessibleName("")  # o texto "Passo X de 3" carrega o estado
            self._dots.append(dot)
            linha.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        linha.addStretch(1)
        self._definir_passo(1)
        return caixa

    # --------------------------------------------------------- cartão/form

    def _cartao(self) -> QStackedWidget:
        self._cartao = QStackedWidget()
        self._cartao.setMaximumWidth(560)
        self._cartao.addWidget(self._pagina_form())
        self._cartao.addWidget(self._pagina_sucesso())
        return self._cartao

    def _pagina_form(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        corpo = QVBoxLayout(card)
        corpo.setContentsMargins(24, 24, 24, 24)
        corpo.setSpacing(_GAP_ROTULO_CAMPO)

        if self._contrato_b:
            corpo.addWidget(self._rotulo("CNPJ da empresa"))
            self._campo_cnpj = self._campo("CNPJ da empresa", "00.000.000/0000-00")
            self._campo_cnpj.textChanged.connect(self._manter_cnpj_formatado)
            self._campo_cnpj.editingFinished.connect(
                lambda: self._validar_cnpj(silencioso_se_vazio=True)
            )
            self._campo_cnpj.returnPressed.connect(self._ativar)
            self._erro_cnpj = self._rotulo_erro()
            # Instalador universal: o CNPJ já vem fixado na instalação.
            cnpj_tenant = self._tenant.get("empresa_cnpj")
            if cnpj_tenant:
                self._campo_cnpj.setText(self._formatar_cnpj(cnpj_tenant))
            corpo.addWidget(self._campo_cnpj)
            corpo.addWidget(self._erro_cnpj)
            razao = self._tenant.get("empresa_razao_social")
            if cnpj_tenant:
                rotulo_instalado = (
                    f"Instalado para: {razao or '—'} · CNPJ {self._formatar_cnpj(cnpj_tenant)}"
                )
                lbl_instalado = EtiquetaQuebra(rotulo_instalado)
                lbl_instalado.setObjectName("ajudaCampo")
                lbl_instalado.setAccessibleName(f"Instalado para: {rotulo_instalado}")
                corpo.addWidget(lbl_instalado)

            corpo.addSpacing(_GAP_ENTRE_GRUPOS)
            corpo.addWidget(self._rotulo("Código da licença"))
            self._campo_codigo = self._campo(
                "Código da licença", "Informe o código enviado por e-mail"
            )
            self._campo_codigo.returnPressed.connect(self._ativar)
            self._erro_codigo = self._rotulo_erro()
            corpo.addWidget(self._campo_codigo)
            corpo.addWidget(self._erro_codigo)
            ajuda = "A ativação acontece uma única vez e precisa de internet."
        else:
            corpo.addWidget(self._rotulo("Chave de produto"))
            self._campo_chave = self._campo(
                "Chave de produto", "XXXX-XXXX-XXXX-XXXX", mono=True, maximo=19
            )
            self._campo_chave.textChanged.connect(self._manter_chave_formatada)
            self._campo_chave.returnPressed.connect(self._ativar)
            self._erro_chave = self._rotulo_erro()
            corpo.addWidget(self._campo_chave)
            corpo.addWidget(self._erro_chave)
            ajuda = "Cole a chave com 4 blocos enviada na contratação."

        corpo.addSpacing(_GAP_ENTRE_GRUPOS)
        lbl_ajuda = EtiquetaQuebra(ajuda)
        lbl_ajuda.setObjectName("ajudaCampo")
        lbl_ajuda.setAccessibleName(f"Ajuda: {ajuda}")
        corpo.addWidget(lbl_ajuda)

        # Erro geral (mensagem do servidor) — junto dos campos (C6).
        self._erro = EtiquetaQuebra("")
        self._erro.setObjectName("erroCampo")
        corpo.addWidget(self._erro)

        self._linha_validando = self._linha_de_validacao()
        self._linha_validando.setVisible(False)
        corpo.addWidget(self._linha_validando)

        corpo.addStretch(1)

        # Ações (A1/B2): Sair à esquerda, primário à direita, altura >= 40 px.
        acoes = QHBoxLayout()
        acoes.setSpacing(8)
        self._botao_sair = self._botao("Sair (Esc)", plano="flat")
        self._botao_sair.clicked.connect(self._solicitar_saida)
        acoes.addWidget(self._botao_sair)
        acoes.addStretch(1)
        self._botao_testar = self._botao("Testar conexão", plano="secondary")
        self._botao_testar.clicked.connect(self._testar)
        acoes.addWidget(self._botao_testar)
        self._botao_ativar = self._botao("Ativar licença (F10)", plano="primary")
        self._botao_ativar.clicked.connect(self._ativar)
        acoes.addWidget(self._botao_ativar)
        corpo.addLayout(acoes)
        return card

    def _linha_de_validacao(self) -> QWidget:
        """Indicador indeterminado + texto + Cancelar (D2)."""
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 8, 0, 0)
        linha.setSpacing(10)
        barra = QProgressBar()
        barra.setObjectName("barraAtiva")
        barra.setRange(0, 0)
        barra.setFixedHeight(4)
        barra.setFixedWidth(90)
        barra.setAccessibleName("Validando com o servidor de licenças")
        linha.addWidget(barra)
        texto = QLabel("Validando com o servidor de licenças…")
        texto.setObjectName("ajudaCampo")
        linha.addWidget(texto, 1)
        self._botao_cancelar = self._botao("Cancelar", plano="flat")
        self._botao_cancelar.clicked.connect(self._cancelar_validacao)
        linha.addWidget(self._botao_cancelar)
        return caixa

    # -------------------------------------------------------- página sucesso

    def _pagina_sucesso(self) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        corpo = QVBoxLayout(card)
        corpo.setContentsMargins(24, 28, 24, 24)
        corpo.setSpacing(8)

        self._sucesso_titulo = EtiquetaQuebra("Licença ativada neste computador.")
        self._sucesso_titulo.setObjectName("tituloSucesso")
        corpo.addWidget(self._sucesso_titulo)

        self._sucesso_resumo = EtiquetaQuebra("")
        self._sucesso_resumo.setObjectName("subtitulo")
        corpo.addWidget(self._sucesso_resumo)

        nota = EtiquetaQuebra("Este computador agora é o servidor da sua gráfica.")
        nota.setObjectName("ajudaCampo")
        corpo.addWidget(nota)

        corpo.addStretch(1)
        self._botao_entrar = self._botao("Entrar", plano="primary")
        self._botao_entrar.setMinimumWidth(180)
        self._botao_entrar.clicked.connect(self.ativada.emit)
        linha = QHBoxLayout()
        linha.addStretch(1)
        linha.addWidget(self._botao_entrar)
        corpo.addLayout(linha)
        return card

    # ------------------------------------------------ detalhes técnicos (C2)

    def _painel_detalhes(self) -> QWidget:
        self._painel_detalhes = QWidget()
        self._painel_detalhes.setObjectName("card")
        self._painel_detalhes.setMaximumWidth(560)
        corpo = QVBoxLayout(self._painel_detalhes)
        corpo.setContentsMargins(20, 18, 20, 18)
        corpo.setSpacing(8)

        c1 = QLabel("Este computador")
        c1.setObjectName("rotuloCampo")
        corpo.addWidget(c1)
        t1 = EtiquetaQuebra(
            "Este computador será o servidor da sua gráfica: guarda o banco de "
            "dados e atende até 5 estações de trabalho do balcão e da produção."
        )
        t1.setObjectName("ajudaCampo")
        corpo.addWidget(t1)

        c2 = QLabel("Sobre a licença")
        c2.setObjectName("rotuloCampo")
        corpo.addWidget(c2)
        t2 = EtiquetaQuebra(
            "A licença é validada pela internet, uma única vez. O código é "
            "enviado por e-mail e também fica disponível no portal de "
            "licenças do fabricante. O sistema confere periodicamente a "
            "situação do contrato com o servidor de licenças."
        )
        t2.setObjectName("ajudaCampo")
        corpo.addWidget(t2)
        self._painel_detalhes.setVisible(False)
        return self._painel_detalhes

    # -------------------------------------------------------------- rodapé

    def _rodape(self) -> QHBoxLayout:
        rodape = QHBoxLayout()
        rodape.setContentsMargins(4, 12, 4, 0)
        rodape.setSpacing(10)
        self._status = QLabel("Servidor local: testando…")
        self._status.setObjectName("statusServidor")
        rodape.addWidget(self._status)
        self._botao_tentar = self._botao("Tentar novamente", plano="flat")
        self._botao_tentar.clicked.connect(self._testar)
        rodape.addWidget(self._botao_tentar)
        rodape.addStretch(1)
        self._botao_detalhes = self._botao("Detalhes técnicos ▸", plano="flat")
        self._botao_detalhes.setCheckable(True)
        self._botao_detalhes.toggled.connect(self._alternar_detalhes)
        rodape.addWidget(self._botao_detalhes)
        return rodape

    def _alternar_detalhes(self, aberto: bool) -> None:
        painel = self._painel_detalhes
        self._botao_detalhes.setText("Detalhes técnicos ▾" if aberto else "Detalhes técnicos ▸")
        if not self._animacoes:
            painel.setVisible(aberto)
            return
        # D7: 160 ms (faixa 120–200 ms), OutCubic; desligado quando o Windows
        # pede "reduzir animações" (SPI_GETCLIENTAREAANIMATION).
        if aberto:
            painel.setMaximumHeight(0)
            painel.show()
            altura = painel.sizeHint().height()
            anim = QPropertyAnimation(painel, b"maximumHeight", self)
            anim.setDuration(160)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(0)
            anim.setEndValue(max(altura, 1))
            anim.finished.connect(lambda: painel.setMaximumHeight(16777215))
        else:
            altura = max(painel.height(), 1)
            anim = QPropertyAnimation(painel, b"maximumHeight", self)
            anim.setDuration(160)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(altura)
            anim.setEndValue(0)
            anim.finished.connect(painel.hide)
        self._animacao_detalhes = anim
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    @staticmethod
    def _animacoes_habilitadas() -> bool:
        """Opção do Windows "Animar controles e elementos dentro de janelas".

        Respeitar a preferência do usuário é parte do D7: com animações
        desligadas no sistema, a interface muda de estado instantaneamente.
        """
        try:
            import ctypes
            import ctypes.wintypes as wintypes

            ligado = wintypes.BOOL()
            ok = ctypes.windll.user32.SystemParametersInfoW(
                0x1042, 0, ctypes.byref(ligado), 0  # SPI_GETCLIENTAREAANIMATION
            )
            return bool(ok and ligado.value)
        except Exception:  # noqa: BLE001 — fora do Windows ou indisponível: liga
            return True

    @staticmethod
    def _linha_tolerancia() -> QLabel:
        # C8: texto neutro — a tolerância offline é uma garantia, não alerta.
        lbl = QLabel(
            "Se a internet cair, o sistema continua funcionando por até 72 horas."
        )
        lbl.setObjectName("ajudaCampo")
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        return lbl

    # ------------------------------------------------------- helpers visuais

    @staticmethod
    def _rotulo(texto: str) -> QLabel:
        lbl = QLabel(texto)  # sentence case, 13 px/600 (A4)
        lbl.setObjectName("rotuloCampo")
        return lbl

    @staticmethod
    def _rotulo_erro() -> QLabel:
        lbl = EtiquetaQuebra("")
        lbl.setObjectName("erroCampo")
        lbl.hide()
        return lbl

    @staticmethod
    def _campo(rotulo: str, placeholder: str, mono: bool = False, maximo: int = 200) -> QLineEdit:
        ed = QLineEdit()
        ed.setPlaceholderText(placeholder)
        ed.setProperty("formAtivacao", "true")
        if mono:
            ed.setProperty("mono", "true")
        ed.setMaxLength(maximo)
        ed.setMinimumHeight(40)
        ed.setAccessibleName(rotulo)
        # Placeholder no cinza secundário (A3): 5,1:1 sobre branco.
        paleta = ed.palette()
        paleta.setColor(QPalette.ColorRole.PlaceholderText, QColor("#6E6E73"))
        ed.setPalette(paleta)
        return ed

    @staticmethod
    def _botao(texto: str, plano: str = "") -> QPushButton:
        b = QPushButton(texto)
        b.setMinimumHeight(40)  # A1: alvo de toque >= 40 px
        b.setAccessibleName(texto)
        if plano == "primary":
            try:
                estado_primario(b)
            except NameError:
                # Fallback: definir propriedade diretamente
                b.setProperty("role", "primary")
                aplicar_estilo(b)
        elif plano == "secondary":
            estado_secundario(b)
        else:
            b.setObjectName("botaoFlat")
        return b

    def _definir_ordem_de_foco(self) -> None:
        if self._contrato_b:
            self.setTabOrder(self._campo_cnpj, self._campo_codigo)
            self.setTabOrder(self._campo_codigo, self._botao_ativar)
        else:
            self.setTabOrder(self._campo_chave, self._botao_ativar)
        self.setTabOrder(self._botao_ativar, self._botao_testar)
        self.setTabOrder(self._botao_testar, self._botao_sair)
        self.setTabOrder(self._botao_sair, self._botao_detalhes)
        self.setTabOrder(self._botao_detalhes, self._botao_tentar)

    # --------------------------------------------------------------- passos

    def _definir_passo(self, passo: int) -> None:
        self._passo = passo
        nomes = _PASSOS_B if self._contrato_b else _PASSOS_C
        self._passo_texto.setText(f"Passo {passo} de 3 · {nomes[passo - 1]}")
        for i, dot in enumerate(self._dots):
            estado = "feito" if i < passo - 1 else ("atual" if i == passo - 1 else "pendente")
            if dot.property("passo") != estado:
                dot.setProperty("passo", estado)
                aplicar_estilo(dot)

    # --------------------------------------------------------- máscaras (D4)

    @staticmethod
    def _ancorar_cursor(
        campo: QLineEdit, posicao: int, antigo: str, formatado: str
    ) -> None:
        """Posiciona o cursor após os mesmos caracteres de CONTEÚDO de antes.

        Separadores (`.`, `/`, `-`) não são conteúdo: inseri-los não pode
        mover o ponto de digitação — era isso que embaralhava o CNPJ
        (32.667.694/0001-01 virava 32.676.400/1010-96). Serve também para a
        chave (letras A–F contam como conteúdo). `posicao` é capturada ANTES
        do `setText`, senão a posição original já se perdeu.
        """
        conteudo_antes = sum(1 for c in antigo[:posicao] if c not in "./-")
        if conteudo_antes <= 0:
            campo.setCursorPosition(0)
            return
        contador = 0
        for i, caractere in enumerate(formatado):
            if caractere not in "./-":
                contador += 1
                if contador == conteudo_antes:
                    campo.setCursorPosition(i + 1)
                    return
        campo.setCursorPosition(len(formatado))  # além do conteúdo: fim do texto

    @staticmethod
    def _formatar_cnpj(texto: str) -> str:
        bruto = "".join(c for c in texto if c.isdigit())[:14]
        if len(bruto) <= 2:
            return bruto
        if len(bruto) <= 5:
            return f"{bruto[:2]}.{bruto[2:]}"
        if len(bruto) <= 8:
            return f"{bruto[:2]}.{bruto[2:5]}.{bruto[5:]}"
        if len(bruto) <= 12:
            return f"{bruto[:2]}.{bruto[2:5]}.{bruto[5:8]}/{bruto[8:]}"
        return f"{bruto[:2]}.{bruto[2:5]}.{bruto[5:8]}/{bruto[8:12]}-{bruto[12:]}"

    def _manter_cnpj_formatado(self, texto: str) -> None:
        formatado = self._formatar_cnpj(texto)
        self._limpar_erro_campo(self._campo_cnpj, self._erro_cnpj)
        if formatado == texto:
            return
        posicao = self._campo_cnpj.cursorPosition()  # antes do setText (âncora)
        self._campo_cnpj.blockSignals(True)
        self._campo_cnpj.setText(formatado)
        self._campo_cnpj.blockSignals(False)
        self._ancorar_cursor(self._campo_cnpj, posicao, texto, formatado)

    @staticmethod
    def _formatar_chave(texto: str) -> str:
        bruto = "".join(c for c in texto.upper() if c in "0123456789ABCDEF")[:16]
        return "-".join(bruto[i : i + 4] for i in range(0, len(bruto), 4))

    def _manter_chave_formatada(self, texto: str) -> None:
        formatado = self._formatar_chave(texto)
        self._limpar_erro_campo(self._campo_chave, self._erro_chave)
        if formatado == texto:
            return
        posicao = self._campo_chave.cursorPosition()  # antes do setText (âncora)
        self._campo_chave.blockSignals(True)
        self._campo_chave.setText(formatado)
        self._campo_chave.blockSignals(False)
        self._ancorar_cursor(self._campo_chave, posicao, texto, formatado)

    # ------------------------------------------------------- validação (C6)

    @staticmethod
    def _cnpj_valido(cnpj: str) -> bool:
        """Dígito verificador do CNPJ (D4) — rejeita sequências repetidas."""
        digitos = "".join(c for c in cnpj if c.isdigit())
        if len(digitos) != 14 or len(set(digitos)) == 1:
            return False
        pesos = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)

        def digito(base: str, pesos_base: tuple) -> str:
            soma = sum(int(d) * p for d, p in zip(base, pesos_base))
            resto = soma % 11
            return "0" if resto < 2 else str(11 - resto)

        d1 = digito(digitos[:12], pesos)
        d2 = digito(digitos[:12] + d1, (6,) + pesos)
        return digitos[12:] == d1 + d2

    @staticmethod
    def _limpar_erro_campo(campo: QLineEdit, rotulo: QLabel) -> None:
        rotulo.setText("")
        rotulo.hide()
        if campo.property("estado") == "erro":
            campo.setProperty("estado", "")
            aplicar_estilo(campo)

    @staticmethod
    def _marcar_erro_campo(campo: QLineEdit, rotulo: QLabel, msg: str) -> None:
        rotulo.setText(msg)
        rotulo.show()
        campo.setProperty("estado", "erro")
        aplicar_estilo(campo)
        campo.setFocus()

    def _validar_cnpj(self, silencioso_se_vazio: bool = False) -> bool:
        digitos = "".join(c for c in self._campo_cnpj.text() if c.isdigit())
        if not digitos:
            if silencioso_se_vazio:
                self._limpar_erro_campo(self._campo_cnpj, self._erro_cnpj)
                return False
            self._marcar_erro_campo(
                self._campo_cnpj, self._erro_cnpj, "Informe o CNPJ da empresa."
            )
            return False
        if not self._cnpj_valido(self._campo_cnpj.text()):
            self._marcar_erro_campo(
                self._campo_cnpj,
                self._erro_cnpj,
                "CNPJ inválido — confira os 14 dígitos.",
            )
            return False
        self._limpar_erro_campo(self._campo_cnpj, self._erro_cnpj)
        return True

    # -------------------------------------------------------- conexão (D3)

    def _testar(self) -> None:
        self._botao_testar.setEnabled(False)
        self._status.setText("Servidor local: testando…")
        aplicar_estilo(self._status)

        def ok(resultado) -> None:
            self._botao_testar.setEnabled(True)
            if resultado:
                self._status.setText("Servidor local: conectado")
                estado_sucesso(self._status)
            else:
                self._status.setText("Servidor local: sem resposta")
                estado_erro(self._status)
            aplicar_estilo(self._status)

        def erro(_) -> None:
            self._botao_testar.setEnabled(True)
            self._status.setText("Servidor local: sem resposta")
            estado_erro(self._status)
            aplicar_estilo(self._status)

        rodar(self._api.testar_comunicacao, ok, erro)

    # --------------------------------------------------------- saída (D5)

    def _solicitar_saida(self) -> None:
        if self._validando:
            return  # durante a validação, Esc não abandona o fluxo sem querer
        resposta = QMessageBox.question(
            self,
            "Sair do PrintGest",
            "Sair do PrintGest? A licença ainda não foi ativada neste computador.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resposta == QMessageBox.StandardButton.Yes:
            self.saida.emit()

    # ------------------------------------------------------ validação (D2)

    def _entrar_em_validacao(self) -> None:
        self._validando = True
        self._cancelado = False
        self._erro.setText("")
        self._linha_validando.setVisible(True)
        self._botao_ativar.setEnabled(False)
        self._botao_ativar.setText("Validando…")
        for campo in self._campos_do_contrato():
            campo.setEnabled(False)

    def _sair_da_validacao(self) -> None:
        self._validando = False
        self._linha_validando.setVisible(False)
        self._botao_ativar.setEnabled(True)
        self._botao_ativar.setText("Ativar licença (F10)")
        for campo in self._campos_do_contrato():
            campo.setEnabled(True)

    def _cancelar_validacao(self) -> None:
        """Aborta a ativação em pleno voo (D2) e descarta o resultado.

        Fecha o cliente dedicado — a requisição em curso é interrompida de
        verdade — e invalida o token da tentativa: qualquer resposta que já
        vinha é descartada. Se o servidor já tiver ativado, uma nova tentativa
        devolve a situação atual e a tela avança normalmente.
        """
        if not self._validando:
            return
        self._tentativa += 1  # invalida o resultado em voo
        cliente, self._cliente_ativacao = self._cliente_ativacao, None
        if cliente is not None:
            try:
                cliente.close()  # aborta o HTTP em andamento
            except Exception:  # noqa: BLE001 — best-effort na thread da UI
                pass
        self._sair_da_validacao()

    def _campos_do_contrato(self) -> list[QLineEdit]:
        if self._contrato_b:
            return [self._campo_cnpj, self._campo_codigo]
        return [self._campo_chave]

    # --------------------------------------------------------- ativar (F1)

    def _ativar(self) -> None:
        if self._validando:
            return
        if self._contrato_b:
            if not self._validar_cnpj():
                return
            codigo = re.sub(r"\s+", "", self._campo_codigo.text().strip())
            if not codigo:
                self._marcar_erro_campo(
                    self._campo_codigo, self._erro_codigo, "Informe o código da licença."
                )
                return
            self._limpar_erro_campo(self._campo_codigo, self._erro_codigo)
            # Capturados na thread da UI: nada de tocar em widget fora dela.
            cnpj = "".join(c for c in self._campo_cnpj.text() if c.isdigit())
            self._entrar_em_validacao()

            def chamada(cliente):
                return self._api.ativar_licenca(
                    self._token, cnpj=cnpj, codigo=codigo, cliente=cliente
                )

            self._disparar(chamada)
            return

        chave = self._campo_chave.text().strip().upper()
        if not _FORMATO_CHAVE.match(chave):
            self._marcar_erro_campo(
                self._campo_chave,
                self._erro_chave,
                "Informe a chave completa (XXXX-XXXX-XXXX-XXXX).",
            )
            return
        self._limpar_erro_campo(self._campo_chave, self._erro_chave)
        self._entrar_em_validacao()

        def chamada(cliente):
            return self._api.ativar_licenca(self._token, chave, cliente=cliente)

        self._disparar(chamada)

    def _disparar(self, fabrica) -> None:
        """Ativa num cliente dedicado, com token de tentativa (D2).

        O token invalida resultados de tentativas superadas: um "Cancelar"
        aborta o pedido de verdade (fecha o cliente) e qualquer resposta que
        já estivesse em voo é descartada — uma nova tentativa nunca recebe o
        resultado de outra.
        """
        self._tentativa += 1
        tentativa = self._tentativa
        cliente = self._api.cliente_para_ativacao()
        self._cliente_ativacao = cliente

        def finalizar() -> None:
            if self._cliente_ativacao is cliente:
                self._cliente_ativacao = None
            try:
                cliente.close()
            except Exception:  # noqa: BLE001 — best-effort na thread da UI
                pass

        def ok(situacao) -> None:
            finalizar()
            if tentativa != self._tentativa:
                return  # tentativa cancelada/superada: descarta
            self._sair_da_validacao()
            self._definir_passo(3)
            self._preencher_sucesso(situacao if isinstance(situacao, dict) else {})
            self._cartao.setCurrentIndex(1)

        def erro(msg: str) -> None:
            finalizar()
            if tentativa != self._tentativa:
                return  # cancelada: o aborto é o comportamento pedido
            self._sair_da_validacao()
            self._definir_passo(1)
            self._erro.setText(msg)
            campo = self._campo_do_erro(msg)
            if campo is not None:
                campo.setFocus()

        rodar(lambda: fabrica(cliente), ok, erro)

    def _campo_do_erro(self, msg: str) -> QLineEdit | None:
        """Foca o campo relacionado à mensagem do servidor, quando houver (C6)."""
        m = msg.lower()
        if "cnpj" in m:
            return self._campo_cnpj
        if "código" in m or "codigo" in m:
            return self._campo_codigo if self._contrato_b else None
        return None

    def _preencher_sucesso(self, situacao: dict) -> None:
        plano = str(situacao.get("plano") or "").strip()
        validade = formatar_datahora(situacao.get("expira_em"))
        partes = []
        if plano:
            partes.append(f"Plano {plano}")
        if validade:
            partes.append(f"válido até {validade}")
        self._sucesso_resumo.setText(" · ".join(partes))
