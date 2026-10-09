"""Tela Principal (mockups 2.x): shell de navegação do ERP desktop.

- Cabeçalho: marca, filial, busca global (clientes/produtos/O.S.), status de
  licença (3 estados), usuário + nível e sair.
- Barra lateral: menu por módulos (§3.2 telas_e_fluxos) filtrado por RBAC
  (oculta itens sem permissão, conforme observação de design §4), com botão de
  colapso e atalhos rápidos ("Nova Venda Balcão", "Nova O.S.").
- Área central: `QStackedWidget` com a página ativa (Início ou módulo).
- Rodapé: relógio, estação (hostname), conectividade do daemon e atalhos
  globais (F2 clientes, F3 produtos, F5 PDV) + versão.
- Em modo leitura, exibe banner amber e repassa o estado às páginas (a API
  também reforça com 423).
"""

from __future__ import annotations

import socket
from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from printgest import APP_NAME, __version__
from printgest.core.api import Api
from printgest.core.rbac import (
    menu_visivel,
    nivel_rotulo,
    pode_abrir,
    rotulo_do_item,
    tem_acesso,
)
from printgest.core.tarefas import rodar
from printgest.ui.busca_global import BuscaGlobal
from printgest.ui.formulario import formatar_moeda
from printgest.ui.modulos import criar_pagina
from printgest.ui.widgets import aplicar_estilo, badge

ITEM_INICIO = "inicio"
_COR_ATRASO = QColor("#dc2626")


def _eh_gerente_ou_mais(nivel: str) -> bool:
    return tem_acesso(nivel, "gerente")


def _eh_operador_ou_mais(nivel: str) -> bool:
    return tem_acesso(nivel, "operador")


class PaginaInicial(QWidget):
    """Tela Início (v2.1 §2.2) — saudação, cards, acesso rápido, entregas e faturamento."""

    filial_obtida = Signal(str)
    navegar = Signal(str)
    conexao_verificada = Signal(bool)

    def __init__(
        self, api: Api, nivel: str, modo_leitura: bool, nome_usuario: str = "Usuário"
    ) -> None:
        super().__init__()
        self._api = api
        self._nivel = nivel
        self._modo_leitura = modo_leitura
        self._dias = 7

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        saudacao = QLabel(self._saudacao(nome_usuario))
        saudacao.setObjectName("titulo")
        layout.addWidget(saudacao)

        self._lbl_relogio_pagina = QLabel(datetime.now().strftime("%H:%M"))
        self._lbl_relogio_pagina.setObjectName("subtitulo")
        layout.addWidget(self._lbl_relogio_pagina)

        if modo_leitura:
            aviso = QLabel(
                "Licença sem renovação — sistema em modo leitura (consultas "
                "apenas, escrita e emissão fiscal bloqueadas)."
            )
            aviso.setObjectName("bannerLeitura")
            layout.addWidget(aviso)

        # ------------------------------------------------ cards do resumo
        self._lbl_vendas_hoje = QLabel("—")
        self._lbl_valor_hoje = QLabel("—")
        self._lbl_vendas_ontem = QLabel("—")
        linha = QHBoxLayout()
        linha.setSpacing(12)
        linha.addWidget(self._medidor("Vendas hoje (qtd)", self._lbl_vendas_hoje))
        linha.addWidget(self._medidor("Vendas hoje (R$)", self._lbl_valor_hoje))
        linha.addWidget(self._medidor("Ontem", self._lbl_vendas_ontem))
        if _eh_gerente_ou_mais(nivel):
            self._lbl_receber_hoje = QLabel("—")
            self._lbl_receber_atrasado = QLabel("—")
            linha.addWidget(self._medidor("A receber hoje", self._lbl_receber_hoje))
            linha.addWidget(self._medidor("A receber atrasado", self._lbl_receber_atrasado))
        if _eh_operador_ou_mais(nivel):
            self._lbl_projetos_producao = QLabel("—")
            self._lbl_projetos_atrasados = QLabel("—")
            linha.addWidget(self._medidor("Projetos em produção", self._lbl_projetos_producao))
            linha.addWidget(self._medidor("Projetos atrasados", self._lbl_projetos_atrasados))
        layout.addLayout(linha)

        # ------------------------------------------------ acesso rápido
        rapido = QWidget()
        rapido.setObjectName("card")
        rl = QVBoxLayout(rapido)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(8)
        rl.addWidget(self._cabecalho_card("Acesso rápido"))
        fila = QHBoxLayout()
        fila.setSpacing(12)
        self._botoes_rapidos: list[QPushButton] = []
        for rotulo, destino in self._atajos_rapidos(nivel):
            botao = QPushButton(rotulo)
            botao.setProperty("role", "primary")
            botao.clicked.connect(
                lambda _=False, d=destino: self.navegar.emit(d)
            )
            self._botoes_rapidos.append(botao)
            fila.addWidget(botao)
        fila.addStretch(1)
        rl.addLayout(fila)
        layout.addWidget(rapido)

        # ------------------------------------------ entregas de hoje (operador+)
        if _eh_operador_ou_mais(nivel):
            entregas = QWidget()
            entregas.setObjectName("card")
            el = QVBoxLayout(entregas)
            el.setContentsMargins(16, 12, 16, 12)
            el.setSpacing(8)
            el.addWidget(self._cabecalho_card("Entregas de hoje e atrasadas"))
            self._lista_entregas = QListWidget()
            self._lista_entregas.itemClicked.connect(
                lambda _item: self.navegar.emit("projetos")
            )
            el.addWidget(self._lista_entregas)
            layout.addWidget(entregas)

        # ------------------------------------- faturamento (gerente+)
        if _eh_gerente_ou_mais(nivel):
            grafico = QWidget()
            grafico.setObjectName("card")
            gl = QVBoxLayout(grafico)
            gl.setContentsMargins(16, 12, 16, 12)
            gl.setSpacing(8)
            topo = QHBoxLayout()
            topo.addWidget(self._cabecalho_card("Faturamento — realizado × previsto"))
            self._combo_dias = QComboBox()
            self._combo_dias.addItem("7 dias", 7)
            self._combo_dias.addItem("30 dias", 30)
            self._combo_dias.currentIndexChanged.connect(self._mudar_dias)
            topo.addWidget(self._combo_dias)
            topo.addStretch(1)
            ver = QPushButton("Ver relatórios →")
            ver.setProperty("role", "ghost")
            ver.clicked.connect(lambda: self.navegar.emit("relatorios"))
            topo.addWidget(ver)
            gl.addLayout(topo)
            self._lbl_grafico = QLabel("Aguardando dados de vendas...", wordWrap=True)
            gl.addWidget(self._lbl_grafico)
            self._barras_realizado: list[tuple[QProgressBar, QLabel]] = []
            self._barras_previsto: list[tuple[QProgressBar, QLabel]] = []
            self._container_realizado = QWidget()
            self._container_previsto = QWidget()
            for container, rotulo in (
                (self._container_realizado, "Realizado"),
                (self._container_previsto, "Previsto"),
            ):
                nome = QLabel(rotulo)
                nome.setProperty("role", "muted")
                gl.addWidget(nome)
                caixas = QHBoxLayout(container)
                caixas.setSpacing(6)
                gl.addWidget(container)
            layout.addWidget(grafico)

        # ------------------------------------------- estoque crítico (operador+)
        if _eh_operador_ou_mais(nivel):
            estoque = QWidget()
            estoque.setObjectName("card")
            el = QVBoxLayout(estoque)
            el.setContentsMargins(16, 12, 16, 12)
            el.setSpacing(8)
            el.addWidget(self._cabecalho_card("Estoque crítico"))
            self._lbl_estoque = QLabel("Aguardando dados de estoque...", wordWrap=True)
            el.addWidget(self._lbl_estoque)
            ver = QPushButton("Ver Produtos")
            ver.setProperty("role", "primary")
            ver.clicked.connect(lambda: self.navegar.emit("produto"))
            el.addWidget(ver)
            layout.addWidget(estoque)

        # ------------------------------------------------------ status operacional
        status = QWidget()
        status.setObjectName("card")
        sl = QVBoxLayout(status)
        sl.setContentsMargins(16, 12, 16, 12)
        sl.setSpacing(8)
        sl.addWidget(self._cabecalho_card("Status operacional"))
        self._lbl_status = QLabel("Verificando daemon...", wordWrap=True)
        sl.addWidget(self._lbl_status)
        layout.addWidget(status)

        layout.addStretch(1)

        self._timer_resumo = QTimer(self)
        self._timer_resumo.setSingleShot(True)
        self._timer_resumo.setInterval(0)
        self._timer_resumo.timeout.connect(self._carregar_resumo)
        self._timer_resumo.start()

        self._timer_relogio_pagina = QTimer(self)
        self._timer_relogio_pagina.setInterval(30000)
        self._timer_relogio_pagina.timeout.connect(self._tick_relogio_pagina)
        self._timer_relogio_pagina.start()

    # ------------------------------------------------------ carregamento

    @staticmethod
    def _saudacao(nome: str) -> str:
        hora = datetime.now().hour
        if hora < 5:
            turno = "Boa madrugada"
        elif hora < 12:
            turno = "Bom dia"
        elif hora < 18:
            turno = "Boa tarde"
        else:
            turno = "Boa noite"
        return f"{turno}, {nome}!"

    @staticmethod
    def _atajos_rapidos(nivel: str) -> list[tuple[str, str]]:
        atalhos = [
            ("Nova venda", "pdv"),
            ("Nova OS/Orçamento", "os"),
            ("Novo cliente", "cliente"),
            ("Emitir NFC-e", "fiscal"),
        ]
        return [(rotulo, d) for rotulo, d in atalhos if pode_abrir(nivel, d)]

    def _tick_relogio_pagina(self) -> None:
        self._lbl_relogio_pagina.setText(datetime.now().strftime("%H:%M"))

    def _mudar_dias(self) -> None:
        self._dias = int(self._combo_dias.currentData() or 7)
        self._carregar_resumo()

    def _carregar_resumo(self) -> None:
        rodar(
            lambda: self._api.resumo_dashboard(self._dias),
            on_ok=self._aplicar_resumo,
            on_erro=self._sem_resumo,
        )
        rodar(self._api.testar_comunicacao, on_ok=self._status_conexao, on_erro=self._sem_status)

    def _aplicar_resumo(self, dados) -> None:
        if not isinstance(dados, dict):
            self._sem_resumo(str(dados))
            return
        self._lbl_vendas_hoje.setText(str(dados.get("vendas_hoje_qtd", 0)))
        self._lbl_valor_hoje.setText(self._moeda(dados.get("vendas_hoje_valor")))
        self._lbl_vendas_ontem.setText(self._texto_ontem(dados))

        if dados.get("filial_nome"):
            self.filial_obtida.emit(dados["filial_nome"])

        if _eh_gerente_ou_mais(self._nivel):
            self._lbl_receber_hoje.setText(self._moeda(dados.get("a_receber_vence_hoje")))
            self._lbl_receber_atrasado.setText(self._moeda(dados.get("a_receber_atrasado")))
            self._preencher_faturamento(
                dados.get("vendas_7_dias"), dados.get("faturamento_previsto")
            )

        if _eh_operador_ou_mais(self._nivel):
            self._lbl_projetos_producao.setText(
                str(dados.get("projetos_em_producao", 0))
            )
            self._lbl_projetos_atrasados.setText(str(dados.get("projetos_atrasados", 0)))
            self._aplicar_estoque(dados.get("estoque_abaixo_minimo"))
            self._aplicar_entregas(dados.get("entregas_hoje"))

    def _aplicar_estoque(self, abaixo) -> None:
        if abaixo is None:
            self._lbl_estoque.setText("Dados de estoque indisponíveis para o seu perfil.")
        else:
            self._lbl_estoque.setText(f"{abaixo} item(ns) com saldo abaixo do mínimo.")

    def _aplicar_entregas(self, entregas) -> None:
        self._lista_entregas.clear()
        itens = entregas if isinstance(entregas, list) else []
        if not itens:
            item = QListWidgetItem("Nenhuma entrega para hoje.")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._lista_entregas.addItem(item)
            return
        for e in itens:
            texto = self._texto_entrega(e)
            linha = QListWidgetItem(texto)
            linha.setData(
                Qt.ItemDataRole.UserRole, {"os_id": e.get("os_id"), "numero": e.get("numero")}
            )
            if e.get("atrasada"):
                linha.setData(Qt.ItemDataRole.ForegroundRole, _COR_ATRASO)
            self._lista_entregas.addItem(linha)

    @staticmethod
    def _texto_entrega(e: dict) -> str:
        cliente = e.get("cliente_nome") or "—"
        servico = e.get("servico") or "—"
        prazo = str(e.get("prazo") or "")[:10]
        status = str(e.get("status") or "").upper()
        prefixo = "⚠ " if e.get("atrasada") else ""
        return f"{prefixo}{cliente} · {servico} · {prazo} · {status}"

    @staticmethod
    def _texto_ontem(dados: dict) -> str:
        qtd = dados.get("vendas_ontem_qtd", 0)
        valor = dados.get("vendas_ontem_valor", 0)
        return f"{qtd} venda(s) · {formatar_moeda(valor) or 'R$ 0,00'}"

    def _preencher_faturamento(self, realizado, previsto) -> None:
        self._preencher_barras(
            self._container_realizado, self._barras_realizado, realizado
        )
        self._preencher_barras(
            self._container_previsto, self._barras_previsto, previsto
        )
        vazio = (not isinstance(realizado, list) or not realizado) and (
            not isinstance(previsto, list) or not previsto
        )
        self._lbl_grafico.setText(
            "Sem dados de faturamento para o período." if vazio else ""
        )

    def _preencher_barras(self, container, barras_ref, serie) -> None:
        barras_ref.clear()
        while container.layout().count():
            item = container.layout().takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not isinstance(serie, list) or not serie:
            return
        valores = [self._num(v.get("valor")) for v in serie if isinstance(v, dict)]
        maior = max(valores) if valores else 0
        for v in serie:
            if not isinstance(v, dict):
                continue
            caixa = QWidget()
            col = QVBoxLayout(caixa)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(2)
            barra = QProgressBar()
            barra.setOrientation(Qt.Orientation.Vertical)
            barra.setTextVisible(False)
            barra.setRange(0, max(1, int(maior)))
            barra.setValue(self._num(v.get("valor")))
            dia = QLabel(self._dia_curto(v.get("data")))
            dia.setProperty("role", "muted")
            dia.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(barra, 1)
            col.addWidget(dia)
            container.layout().addWidget(caixa)
            barras_ref.append((barra, dia))

    def _status_conexao(self, conectado: bool) -> None:
        if self._modo_leitura:
            self._lbl_status.setText("Daemon conectado — sistema em modo leitura.")
        elif conectado:
            self._lbl_status.setText(
                f"Local API Service conectado ({self._api.base_url_display})."
            )
        else:
            self._lbl_status.setText("Local API Service sem resposta — verifique o daemon.")
        self.conexao_verificada.emit(conectado)

    def _sem_status(self, msg: str) -> None:
        self._lbl_status.setText(f"Falha ao verificar o daemon: {msg}")
        self.conexao_verificada.emit(False)

    def _sem_resumo(self, msg) -> None:
        self._lbl_vendas_hoje.setText("—")
        self._lbl_valor_hoje.setText("—")
        self._lbl_vendas_ontem.setText("—")
        if _eh_gerente_ou_mais(self._nivel):
            self._lbl_receber_hoje.setText("—")
            self._lbl_receber_atrasado.setText("—")
            self._lbl_grafico.setText("Gráfico de faturamento indisponível no momento.")
        if _eh_operador_ou_mais(self._nivel):
            self._lbl_projetos_producao.setText("—")
            self._lbl_projetos_atrasados.setText("—")
            self._lbl_estoque.setText("Resumo de estoque indisponível no momento.")

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _num(v) -> int:
        try:
            return int(float(str(v).replace(",", ".").replace("R$", "").strip()))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _moeda(v) -> str:
        return formatar_moeda(v) or "R$ 0,00"

    @staticmethod
    def _dia_curto(data) -> str:
        if not data:
            return "—"
        try:
            d = datetime.strptime(str(data)[:10], "%Y-%m-%d")
        except ValueError:
            return str(data)
        return d.strftime("%d/%m")

    @staticmethod
    def _cabecalho_card(texto: str) -> QLabel:
        rotulo = QLabel(texto)
        rotulo.setObjectName("secaoForm")
        return rotulo

    @staticmethod
    def _medidor(rotulo: str, valor: QLabel) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("cardLow")
        layout = QVBoxLayout(caixa)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        nome = QLabel(rotulo)
        nome.setProperty("role", "muted")
        valor.setObjectName("valorCard")
        layout.addWidget(nome)
        layout.addWidget(valor)
        return caixa


class TelaPrincipal(QMainWindow):
    solicitado_logout = Signal()
    navegado = Signal(str)

    def __init__(
        self,
        api: Api,
        usuario: dict,
        modo_leitura: bool = False,
        base_url: str = "127.0.0.1:8000",
        situacao_licenca: dict | None = None,
    ) -> None:
        super().__init__()
        self._api = api
        self._usuario = usuario
        self._nivel = usuario.get("nivel_acesso", "operador")
        self._modo_leitura = modo_leitura
        self._base_url = base_url
        self._paginas: dict[str, QWidget] = {}
        self._colapsada = False

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 660)

        raiz = QWidget()
        coluna = QVBoxLayout(raiz)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)

        if modo_leitura:
            coluna.addWidget(self._banner_modo_leitura())

        coluna.addWidget(self._cabecalho())

        corpo = QWidget()
        linha = QHBoxLayout(corpo)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(0)
        self._sidebar = self._barra_lateral()
        linha.addWidget(self._sidebar)
        linha.addWidget(self._stack(), 1)
        coluna.addWidget(corpo, 1)
        coluna.addWidget(self._rodape())

        self.setCentralWidget(raiz)
        self._instalar_atalhos()
        if situacao_licenca is not None:
            # Licença já consultada no login (token de sessão): evita o 2º GET.
            self._licenca(situacao_licenca)
        else:
            self._timer_licenca = QTimer(self)
            self._timer_licenca.setSingleShot(True)
            self._timer_licenca.setInterval(0)
            self._timer_licenca.timeout.connect(self._carregar_licenca)
            self._timer_licenca.start()

    # -------------------------------------------------------------- topo

    def _cabecalho(self) -> QWidget:
        cabecalho = QWidget()
        cabecalho.setObjectName("cabecalho")
        linha = QHBoxLayout(cabecalho)
        linha.setContentsMargins(20, 10, 20, 10)
        linha.setSpacing(12)

        marca = QLabel(APP_NAME)
        marca.setObjectName("marca")
        linha.addWidget(marca)

        self._lbl_filial = QLabel(self._usuario.get("filial_nome", ""))
        self._lbl_filial.setProperty("role", "muted")
        linha.addWidget(self._lbl_filial)

        servidor = badge(f"Daemon: {self._base_url}", "primary")
        self._lbl_licenca = badge("", "success")
        linha.addWidget(servidor)
        linha.addWidget(self._lbl_licenca)
        linha.addStretch(1)

        self._busca = BuscaGlobal(self._api, self._nivel)
        self._busca.navegar.connect(self._navegar)
        linha.addWidget(self._busca)

        nome = QLabel(self._usuario.get("nome", self._usuario.get("login", "?")))
        nome.setProperty("role", "muted")
        linha.addWidget(nome)
        linha.addWidget(badge(nivel_rotulo(self._nivel)))

        sair = QPushButton("Sair")
        sair.setProperty("role", "ghost")
        sair.clicked.connect(self._sair)
        linha.addWidget(sair)
        return cabecalho

    def _carregar_licenca(self) -> None:
        rodar(
            lambda: self._api.situacao_licenca(self._api.token),
            on_ok=self._licenca,
            on_erro=self._sem_licenca,
        )

    def _licenca(self, sit: dict) -> None:
        if not isinstance(sit, dict):
            self._sem_licenca("resposta inesperada")
            return
        self._lbl_licenca.setText(self._texto_licenca(sit, self._modo_leitura))
        self._lbl_licenca.setProperty("badgeStyle", self._estilo_licenca(sit, self._modo_leitura))
        aplicar_estilo(self._lbl_licenca)

    def _sem_licenca(self, msg) -> None:
        self._lbl_licenca.setText(self._texto_licenca({}, self._modo_leitura))
        self._lbl_licenca.setProperty(
            "badgeStyle", self._estilo_licenca({}, self._modo_leitura)
        )
        aplicar_estilo(self._lbl_licenca)

    @staticmethod
    def _texto_licenca(sit: dict, modo_leitura: bool) -> str:
        if modo_leitura:
            return "Modo Leitura"
        status = sit.get("status")
        if status == "ativa":
            return "Licença Ativa"
        if status:
            return "Licença pendente"
        return "Verificando licença..."

    @staticmethod
    def _estilo_licenca(sit: dict, modo_leitura: bool) -> str:
        if modo_leitura or sit.get("modo_leitura"):
            return "erro"
        if sit.get("status") == "ativa":
            return "success"
        return "atencao"

    def _banner_modo_leitura(self) -> QWidget:
        banner = QWidget()
        banner.setObjectName("bannerAmber")
        linha = QHBoxLayout(banner)
        linha.setContentsMargins(24, 8, 24, 8)
        linha.setSpacing(10)
        titulo = QLabel("Sistema em modo leitura — apenas consultas")
        titulo.setStyleSheet("font-weight: 700; font-size: 13px;")
        linha.addWidget(titulo)
        linha.addWidget(badge("Escritas bloqueadas", "atencao"))
        linha.addStretch(1)
        return banner

    def _barra_lateral(self) -> QWidget:
        lateral = QWidget()
        lateral.setObjectName("sidebar")
        lateral.setFixedWidth(224)
        layout = QVBoxLayout(lateral)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(2)

        self._btn_colapso = self._botao_menu("«", checkavel=False)
        self._btn_colapso.clicked.connect(self._alternar_colapso)
        layout.addWidget(self._btn_colapso)

        inicio = self._botao_menu("Início", checkavel=True)
        inicio.setChecked(True)
        inicio.clicked.connect(lambda: self._navegar(ITEM_INICIO))
        layout.addWidget(inicio)
        self._btn_menu = {ITEM_INICIO: inicio}
        self._itens_lateral: list[QWidget] = []

        for grupo, itens in menu_visivel(self._nivel):
            rotulo = QLabel(grupo.upper())
            rotulo.setObjectName("grupoMenu")
            layout.addWidget(rotulo)
            self._itens_lateral.append(rotulo)
            for item in itens:
                botao = self._botao_menu(item["rotulo"])
                botao.clicked.connect(
                    lambda _=False, i=item["id"]: self._navegar(i)
                )
                self._btn_menu[item["id"]] = botao
                self._itens_lateral.append(botao)
                layout.addWidget(botao)

        layout.addStretch(1)

        # Atalhos rápidos no fim da lateral (RBAC próprio via `pode_abrir`).
        if pode_abrir(self._nivel, "pdv"):
            nova_venda = self._botao_menu("Nova Venda Balcão", checkavel=False)
            nova_venda.clicked.connect(lambda: self._navegar("pdv"))
            layout.addWidget(nova_venda)
        if pode_abrir(self._nivel, "projetos"):
            nova_os = self._botao_menu("Nova OS", checkavel=False)
            nova_os.clicked.connect(lambda: self._navegar("projetos"))
            layout.addWidget(nova_os)
        return lateral

    def _alternar_colapso(self) -> None:
        self._colapsada = not self._colapsada
        largura = 64 if self._colapsada else 224
        self._sidebar.setFixedWidth(largura)
        self._btn_colapso.setText("»" if self._colapsada else "«")
        for widget in self._itens_lateral:
            widget.setVisible(not self._colapsada)
        self._btn_menu[ITEM_INICIO].setVisible(True)
        aplicar_estilo(self._sidebar)

    def _botao_menu(self, texto: str, checkavel: bool = True) -> QPushButton:
        botao = QPushButton(texto)
        botao.setProperty("nav", "true")
        botao.setCheckable(checkavel)
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        return botao

    def _stack(self) -> QStackedWidget:
        self._stack_paginas = QStackedWidget()
        self._pagina_inicio = PaginaInicial(
            self._api,
            self._nivel,
            self._modo_leitura,
            nome_usuario=self._usuario.get("nome", self._usuario.get("login", "Usuário")),
        )
        self._pagina_inicio.filial_obtida.connect(self._definir_filial)
        self._pagina_inicio.navegar.connect(self._navegar)
        self._stack_paginas.addWidget(self._pagina_inicio)
        return self._stack_paginas

    def _definir_filial(self, nome: str) -> None:
        self._lbl_filial.setText(nome)
        self._lbl_filial.setToolTip("Filial do resumo carregado")

    def _rodape(self) -> QWidget:
        rodape = QWidget()
        rodape.setObjectName("rodape")
        linha = QHBoxLayout(rodape)
        linha.setContentsMargins(16, 6, 16, 6)
        linha.setSpacing(14)

        self._lbl_relogio = QLabel(datetime.now().strftime("%H:%M:%S"))
        self._lbl_relogio.setProperty("role", "muted")
        linha.addWidget(self._lbl_relogio)
        self._timer_relogio = QTimer(self)
        self._timer_relogio.setInterval(1000)
        self._timer_relogio.timeout.connect(self._tick_relogio)
        self._timer_relogio.start()

        host = QLabel(socket.gethostname())
        host.setProperty("role", "muted")
        linha.addWidget(host)

        self._lbl_conexao = QLabel("● —")
        self._lbl_conexao.setProperty("role", "muted")
        linha.addWidget(self._lbl_conexao)
        # A Tela Início já consulta /health ao abrir; o rodapé reaproveita o
        # resultado em vez de disparar uma 2ª chamada no arranque.
        self._pagina_inicio.conexao_verificada.connect(self._pintar_conexao)

        for kbd, texto in [
            ("F2", "Clientes"),
            ("F3", "Produtos"),
            ("F5", "PDV"),
        ]:
            hint = QLabel(f"[{kbd}] {texto}")
            hint.setProperty("role", "muted")
            linha.addWidget(hint)
        linha.addStretch(1)
        versao = QLabel(f"v{__version__}")
        versao.setProperty("role", "muted")
        linha.addWidget(versao)

        self._timer_conexao = QTimer(self)
        self._timer_conexao.setInterval(30000)
        self._timer_conexao.timeout.connect(self._verificar_conexao)
        self._timer_conexao.start()
        return rodape

    def _tick_relogio(self) -> None:
        self._lbl_relogio.setText(datetime.now().strftime("%H:%M:%S"))

    def _verificar_conexao(self) -> None:
        if not self.isVisible():
            return  # janela oculta/minimizada: sem consulta em segundo plano
        rodar(
            self._api.testar_comunicacao,
            on_ok=self._pintar_conexao,
            on_erro=lambda _msg: self._pintar_conexao(False),
        )

    def _pintar_conexao(self, ok: bool) -> None:
        self._lbl_conexao.setText("● online" if ok else "○ offline")
        self._lbl_conexao.setProperty("role", "success" if ok else "error")
        aplicar_estilo(self._lbl_conexao)

    # ------------------------------------------------------------ navegação

    def _instalar_atalhos(self) -> None:
        atalhos = {"F2": "cliente", "F3": "produto", "F5": "pdv"}
        for tecla, item_id in atalhos.items():
            atalho = QShortcut(QKeySequence(tecla), self)
            atalho.activated.connect(lambda i=item_id: self._navegar(i))

    def _navegar(self, item_id: str) -> None:
        if item_id != ITEM_INICIO and not pode_abrir(self._nivel, item_id):
            return
        if item_id == ITEM_INICIO:
            self._marcar(ITEM_INICIO)
            self._stack_paginas.setCurrentWidget(self._pagina_inicio)
            self.navegado.emit(ITEM_INICIO)
            return

        pagina = self._paginas.get(item_id)
        if pagina is None:
            rotulo = rotulo_do_item(item_id)
            pagina = criar_pagina(item_id, rotulo, self._api, self._modo_leitura)
            self._paginas[item_id] = pagina
            self._stack_paginas.addWidget(pagina)
        self._marcar(item_id)
        self._stack_paginas.setCurrentWidget(pagina)
        self.navegado.emit(item_id)

    def _marcar(self, item_id: str) -> None:
        for btn_id, botao in self._btn_menu.items():
            botao.setChecked(btn_id == item_id)
            aplicar_estilo(botao)
        if item_id in self._btn_menu:
            self._btn_menu[item_id].setFocus()

    # ------------------------------------------------------------ logout

    def _sair(self) -> None:
        self._api.logout()
        self.solicitado_logout.emit()