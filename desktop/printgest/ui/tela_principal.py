"""Tela Principal (mockups 2.x): shell de navegação do ERP desktop.

- Cabeçalho: marca, filial, indicador de servidor local, busca global
  (clientes/produtos/O.S.), sino (alertas), engrenagem (preferências), licença
  clicável e um único menu de usuário (preferências/trocar senha/sair).
- Barra lateral: menu por módulos (§3.2 telas_e_fluxos) filtrado por RBAC
  (oculta itens sem permissão, conforme observação de design §4) e botão de
  colapso. As ações de criação ficam só no "Acesso rápido" do Início.
- Área central: `QStackedWidget` com a página ativa (Início ou módulo).
- Rodapé: relógio, estação (hostname), conectividade do servidor local e
  atalhos globais (F2 clientes, F3 produtos, F5 PDV) + versão.
- Em modo leitura, exibe banner amber e repassa o estado às páginas (a API
  também reforça com 423).
- Em tolerância, exibe banner **não bloqueante** com o prazo final e o tempo
  restante recomposto a cada minuto (doc de integração §9.3 / E5).
"""

from __future__ import annotations

import socket
from datetime import datetime, timezone

from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
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
from printgest.ui import animacao
from printgest.ui.busca_global import MODULO_POR_ENTIDADE, BuscaGlobal
from printgest.ui.formulario import formatar_moeda
from printgest.ui.modulos import criar_pagina
from printgest.ui.widgets_atualizacao import NotificacaoAtualizacao
from printgest.ui.widgets import (
    ConteudoRolavel,
    ElideLabel,
    PilhaResponsiva,
    SkeletonCartao,
    aplicar_estilo,
    aplicar_estado,
    estado_sucesso,
    estado_erro,
    estado_atencao,
    estado_muted,
    estado_ghost,
    estado_secundario,
    estado_primario,
    badge,
    formatar_datahora,
)

ITEM_INICIO = "inicio"
_COR_ATRASO = QColor("#dc2626")
_PERFIL_CURTO = {
    "admin": "Admin",
    "gerente": "Gerente",
    "operador": "Operador",
    "caixa": "Caixa",
}
# Rótulos curtos para o trilho colapsado (64 px). Nunca escondemos os links:
# o menu inteiro continua clicável, com tooltip/accessibleName completos.
_ITEM_CURTO = {
    "inicio": "⌂", "pdv": "PDV", "projetos": "PRJ", "agendamento": "AG",
    "cliente": "CLI", "fornecedor": "FOR", "produto": "PRD", "servico": "SRV",
    "categoria": "CAT", "funcionario": "FNC", "financeiro": "FIN",
    "fiscal": "FIS", "estoque": "EST", "relatorios": "REL",
    "configuracoes": "CFG", "filiais": "FIL", "consolidacao": "CON",
}


def _rotulo_curto(item_id: str, rotulo: str) -> str:
    return _ITEM_CURTO.get(item_id, rotulo.strip()[:2].upper() or "•")


def _eh_gerente_ou_mais(nivel: str) -> bool:
    return tem_acesso(nivel, "gerente")


def _eh_operador_ou_mais(nivel: str) -> bool:
    return tem_acesso(nivel, "operador")


class CartaoClique(QWidget):
    """Cartão clicável (KPI da home): cursor de mão + sinal no mouse press."""

    clicado = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, evento) -> None:  # noqa: N802 (API do Qt)
        super().mousePressEvent(evento)
        self.clicado.emit()


def _momento(valor: object) -> datetime | None:
    """ISO-8601 (com ou sem fuso) vindo do daemon → `datetime` com fuso (UTC se ausente)."""
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def tempo_restante(valor: object, agora: datetime | None = None) -> str:
    """Tempo restante em texto curto: `2 dias e 21 h`, `3 h e 12 min`, `8 min`.

    Vazio quando o prazo não é legível; `menos de 1 min` quando já passou.
    """
    fim = _momento(valor)
    if fim is None:
        return ""
    agora = agora or _agora_utc()
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    segundos = int((fim - agora).total_seconds())
    if segundos <= 0:
        return "menos de 1 min"
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    if dias:
        return f"{dias} dia{'s' if dias > 1 else ''} e {horas} h"
    if horas:
        return f"{horas} h e {minutos} min"
    return f"{max(minutos, 1)} min"


def fracao_tolerancia(sit: dict, agora: datetime | None = None) -> float | None:
    """Fração (0..1) da janela de tolerância ainda disponível.

    `None` quando não há janela (licença vitalícia ou payload sem `expira_em`)
    — nesse caso o banner esconde a barra de progresso.
    """
    fim = _momento(sit.get("tolerancia_expira_em"))
    inicio = _momento(sit.get("expira_em"))
    if fim is None or inicio is None or fim <= inicio:
        return None
    agora = agora or _agora_utc()
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=timezone.utc)
    total = (fim - inicio).total_seconds()
    return min(1.0, max(0.0, (fim - agora).total_seconds() / total))


def mensagem_tolerancia(sit: dict) -> str:
    """Mensagem do banner não bloqueante (doc de integração RedGest §9.3)."""
    prazo = formatar_datahora(sit.get("tolerancia_expira_em"))
    if prazo:
        return (
            "Sem conexão com o servidor de licenças. O PrintGest continuará "
            f"funcionando normalmente até {prazo}."
        )
    return (
        "Sem conexão com o servidor de licenças. O PrintGest continuará "
        "funcionando normalmente durante a tolerância."
    )


class PaginaInicial(QWidget):
    """Tela Início (v2.1 §2.2) — saudação, 3 KPIs, acesso rápido, entregas,
    faturamento e indicador de estoque crítico.

    O conteúdo fica dentro de um `QScrollArea` (scroll vertical quando a janela
    for menor que o conteúdo) e os cartões usam layouts/`QSizePolicy` — nunca
    altura fixa.
    """

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
        # Skeleton do primeiro carregamento do resumo: barras nos cards de
        # dados até a resposta chegar; recargas seguintes mantêm os valores
        # antigos (sem piscar) — doc quick-reference `loading-states`.
        self._skeletons: list[SkeletonCartao] = []
        self._resumo_recebido = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        conteudo = ConteudoRolavel()
        self._scroll.setWidget(conteudo)
        raiz.addWidget(self._scroll)

        layout = QVBoxLayout(conteudo)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        saudacao = ElideLabel(self._saudacao(nome_usuario))
        saudacao.setObjectName("titulo")
        layout.addWidget(saudacao)

        if modo_leitura:
            aviso = QLabel(
                "Licença sem renovação — sistema em modo leitura (consultas "
                "apenas, escrita e emissão fiscal bloqueadas)."
            )
            aviso.setObjectName("bannerLeitura")
            aviso.setWordWrap(True)
            layout.addWidget(aviso)

        # Alerta de conexão — só aparece quando o servidor local falha (o card
        # "Status operacional" foi removido do Início para não duplicar info).
        self._alerta_conexao = QLabel("")
        self._alerta_conexao.setObjectName("bannerErro")
        self._alerta_conexao.setWordWrap(True)
        self._alerta_conexao.setVisible(False)
        layout.addWidget(self._alerta_conexao)

        # ---------------------------------------------------- KPIs (3 cartões)
        self._kpi_vendas_valor = ElideLabel("—")
        self._kpi_vendas_sub = ElideLabel("")

        # Linha de estado do resumo: quando os dados chegaram + retry em falha
        # (revisão de telas P0#1: zero real x carregando/falha).
        estado_resumo = QWidget()
        er_linha = QHBoxLayout(estado_resumo)
        er_linha.setContentsMargins(0, 0, 0, 0)
        er_linha.setSpacing(8)
        self._lbl_atualizado = QLabel("")
        estado_muted(self._lbl_atualizado)
        er_linha.addWidget(self._lbl_atualizado)
        er_linha.addStretch(1)
        self._btn_retry_resumo = QPushButton("Tentar novamente")
        self._btn_retry_resumo.setProperty("link", "true")
        self._btn_retry_resumo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_retry_resumo.setVisible(False)
        self._btn_retry_resumo.clicked.connect(self._carregar_resumo)
        er_linha.addWidget(self._btn_retry_resumo)
        layout.addWidget(estado_resumo)

        # KPIs em largura total (cards com stretch igual), clicáveis para o
        # detalhe do módulo correspondente (revisão de telas P1#7).
        grade = QHBoxLayout()
        grade.setSpacing(12)
        self._grade_kpi = grade
        grade.addWidget(
            self._cartao_kpi(
                "Vendas hoje", self._kpi_vendas_valor, self._kpi_vendas_sub, "pdv"
            ),
            1,
        )
        if _eh_gerente_ou_mais(nivel):
            self._kpi_receber_valor = ElideLabel("—")
            self._kpi_receber_sub = ElideLabel("")
            self._kpi_pagar_valor = ElideLabel("—")
            self._kpi_pagar_sub = ElideLabel("")
            grade.addWidget(
                self._cartao_kpi(
                    "A receber",
                    self._kpi_receber_valor,
                    self._kpi_receber_sub,
                    "financeiro",
                ),
                1,
            )
            grade.addWidget(
                self._cartao_kpi(
                    "A pagar", self._kpi_pagar_valor, self._kpi_pagar_sub, "financeiro"
                ),
                1,
            )
        if _eh_operador_ou_mais(nivel):
            self._kpi_projetos_valor = ElideLabel("—")
            self._kpi_projetos_sub = ElideLabel("")
            grade.addWidget(
                self._cartao_kpi(
                    "O.S. em produção",
                    self._kpi_projetos_valor,
                    self._kpi_projetos_sub,
                    "os",
                ),
                1,
            )
        layout.addLayout(grade)

        # -------------------------------- "O que preciso fazer agora" (P1#6)
        if _eh_operador_ou_mais(nivel):
            pendencias = QWidget()
            pendencias.setObjectName("card")
            pl = QVBoxLayout(pendencias)
            pl.setContentsMargins(16, 12, 16, 12)
            pl.setSpacing(8)
            pl.addWidget(self._cabecalho_card("O que preciso fazer agora"))
            self._lista_pendencias = QListWidget()
            self._lista_pendencias.setMinimumHeight(96)
            self._lista_pendencias.setAccessibleName("Pendências do dia")
            self._lista_pendencias.itemClicked.connect(self._abrir_pendencia)
            pl.addWidget(self._lista_pendencias)
            self._vazio_pendencias = QLabel("Tudo em dia por aqui. 🎉")
            self._vazio_pendencias.setObjectName("vazioCard")
            self._vazio_pendencias.setWordWrap(True)
            self._vazio_pendencias.setVisible(False)
            pl.addWidget(self._vazio_pendencias)
            self._skeletons.append(SkeletonCartao(pendencias))
            layout.addWidget(pendencias)

        # ---------------------------------------------------- acesso rápido
        rapido = QWidget()
        rapido.setObjectName("card")
        rl = QVBoxLayout(rapido)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(8)
        rl.addWidget(self._cabecalho_card("Acesso rápido"))
        fila = QHBoxLayout()
        fila.setSpacing(12)
        self._botoes_rapidos: list[QPushButton] = []
        # Uma ação principal por tela (quick-reference §4 `primary-action`): só o
        # primeiro atalho recebe o preenchimento de acento; os demais ficam
        # secundários, para o olho não disputar quatro pesos iguais.
        for indice, (rotulo, destino, tecla) in enumerate(self._atajos_rapidos(nivel)):
            # Atalho visível no próprio botão (revisão de telas P1#8): não
            # depende do rodapé; ações mistas viram dois botões.
            texto = f"{rotulo}  ({tecla})" if tecla else rotulo
            botao = QPushButton(texto)
            # Primeiro atalho é primário, os demais são secundários
            if indice == 0:
                estado_primario(botao)
            else:
                estado_secundario(botao)
            botao.setAccessibleName(rotulo)
            botao.setMinimumHeight(32)
            botao.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            botao.clicked.connect(lambda _=False, d=destino: self.navegar.emit(d))
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
            self._lista_entregas.setMinimumHeight(120)
            self._lista_entregas.setAccessibleName("Entregas de hoje e atrasadas")
            # P3/1024px: nomes longos de clientes geravam rolagem horizontal no
            # card de entregas; textos longos elidem e o tooltip traz o completo.
            self._lista_entregas.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self._lista_entregas.setWordWrap(False)
            self._lista_entregas.itemClicked.connect(
                lambda _item: self.navegar.emit("projetos")
            )
            el.addWidget(self._lista_entregas)
            # Estado vazio com convite à ação: nunca um card em branco
            # (quick-reference §8 `empty-states`). Padding respi­rado e sem
            # link solto na borda (revisão de telas P1#9).
            self._vazio_entregas = QWidget()
            vazio = QVBoxLayout(self._vazio_entregas)
            vazio.setContentsMargins(0, 10, 0, 10)
            vazio.setSpacing(6)
            msg = QLabel("Nenhuma entrega para hoje ou atrasada.")
            msg.setObjectName("vazioCard")
            msg.setWordWrap(True)
            vazio.addWidget(msg)
            vazio.addStretch(1)
            el.addWidget(self._vazio_entregas)
            self._vazio_entregas.setVisible(False)
            self._skeletons.append(SkeletonCartao(entregas))
            layout.addWidget(entregas)

        # ------------------------------------------- estoque crítico (operador+)
        # Acima do gráfico: é acionável e não deve cair abaixo da dobra (P1#6).
        if _eh_operador_ou_mais(nivel):
            estoque = QWidget()
            estoque.setObjectName("card")
            el = QVBoxLayout(estoque)
            el.setContentsMargins(16, 12, 16, 12)
            el.setSpacing(6)
            el.addWidget(self._cabecalho_card("Estoque crítico"))
            self._lbl_estoque = ElideLabel("Consultando estoque...")
            estado_muted(self._lbl_estoque)
            el.addWidget(self._lbl_estoque)
            self._btn_estoque = QPushButton("Ver produtos com estoque baixo")
            self._btn_estoque.setProperty("link", "true")
            self._btn_estoque.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_estoque.clicked.connect(lambda: self.navegar.emit("produto"))
            self._btn_estoque.setVisible(False)
            el.addWidget(self._btn_estoque)
            self._skeletons.append(SkeletonCartao(estoque))
            layout.addWidget(estoque)

        # ------------------------------------- faturamento (gerente+)
        # Um único gráfico com barras pareadas por dia (Realizado | Previsto)
        # + linha de base — substitui as duas séries empilhadas (P0#2/#3).
        if _eh_gerente_ou_mais(nivel):
            grafico = QWidget()
            grafico.setObjectName("card")
            grafico.setMinimumHeight(220)
            gl = QVBoxLayout(grafico)
            gl.setContentsMargins(16, 12, 16, 12)
            gl.setSpacing(8)
            gl.addWidget(self._cabecalho_card("Faturamento"))
            topo = QHBoxLayout()
            legenda_r = QLabel("■ Realizado")
            legenda_r.setObjectName("legendaSerie")
            topo.addWidget(legenda_r)
            legenda_p = QLabel("□ Previsto")
            legenda_p.setObjectName("legendaSerie")
            topo.addWidget(legenda_p)
            topo.addStretch(1)
            self._combo_dias = QComboBox()
            self._combo_dias.addItem("7 dias", 7)
            self._combo_dias.addItem("30 dias", 30)
            self._combo_dias.currentIndexChanged.connect(self._mudar_dias)
            topo.addWidget(self._combo_dias)
            ver = QPushButton("Ver relatórios →")
            estado_ghost(ver)
            ver.clicked.connect(lambda: self.navegar.emit("relatorios"))
            topo.addWidget(ver)
            gl.addLayout(topo)
            self._lbl_grafico = ElideLabel("")
            estado_muted(self._lbl_grafico)
            gl.addWidget(self._lbl_grafico)
            self._container_barras = QWidget()
            self._container_barras.setMinimumHeight(120)
            self._container_barras.setAccessibleName(
                "Faturamento realizado e previsto por dia"
            )
            gl.addWidget(self._container_barras, 1)
            # Linha de base: dias zerados não ficam "flutuando" sem referência.
            base = QFrame()
            base.setFrameShape(QFrame.Shape.HLine)
            base.setObjectName("linhaBaseGrafico")
            gl.addWidget(base)
            self._skeletons.append(SkeletonCartao(grafico))
            layout.addWidget(grafico)

        layout.addStretch(1)

        self._timer_resumo = QTimer(self)
        self._timer_resumo.setSingleShot(True)
        self._timer_resumo.setInterval(0)
        self._timer_resumo.timeout.connect(self._carregar_resumo)
        self._timer_resumo.start()

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
    def _atajos_rapidos(nivel: str) -> list[tuple[str, str, str | None]]:
        """Ações rápidas: (rótulo, destino, tecla global visível ou None)."""
        atalhos = [
            ("Nova venda", "pdv", "F5"),
            ("Nova O.S.", "os", None),
            ("Novo orçamento", "orcamento", None),
            ("Novo cliente", "cliente", "F2"),
            ("Emitir NFC-e", "fiscal", None),
        ]
        return [(rotulo, d, t) for rotulo, d, t in atalhos if pode_abrir(nivel, d)]

    def _mudar_dias(self) -> None:
        self._dias = int(self._combo_dias.currentData() or 7)
        self._carregar_resumo()

    def recarregar(self) -> None:
        """Recarrega KPIs/pendências ao voltar para o Início (chamado por
        `TelaPrincipal._navegar`)."""
        self._carregar_resumo()

    def _carregar_resumo(self) -> None:
        if not self._resumo_recebido:
            # Primeiro carregamento: skeleton nos cards de dados (recargas
            # seguintes mantêm os valores antigos na tela, sem piscar).
            for skeleton in self._skeletons:
                skeleton.mostrar()
        rodar(
            lambda: self._api.resumo_dashboard(self._dias),
            on_ok=self._aplicar_resumo,
            on_erro=self._sem_resumo,
        )
        rodar(self._api.testar_comunicacao, on_ok=self._status_conexao, on_erro=self._sem_status)

    def _aplicar_resumo(self, dados) -> None:
        self._resumo_recebido = True
        for skeleton in self._skeletons:
            skeleton.ocultar()
        if not isinstance(dados, dict):
            self._sem_resumo(str(dados))
            return

        qtd_hoje = self._int(dados.get("vendas_hoje_qtd"))
        qtd_ontem = self._int(dados.get("vendas_ontem_qtd"))
        self._kpi_vendas_valor.setText(self._moeda(dados.get("vendas_hoje_valor")))
        self._kpi_vendas_sub.setText(
            f"{self._plural(qtd_hoje, 'venda', 'vendas')} · ontem: {qtd_ontem}"
        )
        # Dado fresco com carimbo de hora (P0#1): distingue zero real de
        # carregando/falha e diz quando foi a última leitura.
        self._lbl_atualizado.setText(f"Atualizado às {datetime.now().strftime('%H:%M')}")
        self._btn_retry_resumo.setVisible(False)

        if dados.get("filial_nome"):
            self.filial_obtida.emit(dados["filial_nome"])

        if _eh_gerente_ou_mais(self._nivel):
            self._kpi_receber_valor.setText(self._moeda(dados.get("a_receber_vence_hoje")))
            self._kpi_receber_sub.setText(
                f"atrasado: {self._moeda(dados.get('a_receber_atrasado'))}"
            )
            self._kpi_pagar_valor.setText(self._moeda(dados.get("a_pagar_vence_hoje")))
            self._kpi_pagar_sub.setText("vence hoje")
            self._preencher_faturamento(
                dados.get("vendas_7_dias"), dados.get("faturamento_previsto")
            )

        if _eh_operador_ou_mais(self._nivel):
            atrasados = self._int(dados.get("projetos_atrasados"))
            self._kpi_projetos_valor.setText(
                str(self._int(dados.get("projetos_em_producao")))
            )
            self._kpi_projetos_sub.setText(
                self._plural(atrasados, "atrasado", "atrasados")
            )
            self._aplicar_estoque(dados.get("estoque_abaixo_minimo"))
            self._aplicar_entregas(dados.get("entregas_hoje"))
            self._aplicar_pendencias(dados.get("pendencias"))

    def _aplicar_estoque(self, abaixo) -> None:
        if abaixo is None:
            self._lbl_estoque.setText("Dados de estoque indisponíveis para o seu perfil.")
            estado_muted(self._lbl_estoque)
            self._btn_estoque.setVisible(False)
        elif self._int(abaixo) > 0:
            n = self._int(abaixo)
            self._lbl_estoque.setText(
                f"{self._plural(n, 'item', 'itens')} abaixo do mínimo"
            )
            # Ícone textual junto da cor: o estado não depende só do verde/laranja
            # (quick-reference §1 `color-not-only`).
            estado_atencao(self._lbl_estoque)
            self._btn_estoque.setVisible(True)
        else:
            self._lbl_estoque.setText("✓ Nenhum item abaixo do mínimo")
            estado_sucesso(self._lbl_estoque)
            self._btn_estoque.setVisible(False)
        self._lbl_estoque.setAccessibleName(self._lbl_estoque.text())

    def _aplicar_entregas(self, entregas) -> None:
        self._lista_entregas.clear()
        itens = entregas if isinstance(entregas, list) else []
        if not itens:
            # Vazio: esconde a lista e mostra o convite à ação.
            self._lista_entregas.setVisible(False)
            self._vazio_entregas.setVisible(True)
            return
        self._vazio_entregas.setVisible(False)
        self._lista_entregas.setVisible(True)
        for e in itens:
            texto = self._texto_entrega(e)
            linha = QListWidgetItem(texto)
            linha.setToolTip(texto)
            linha.setData(
                Qt.ItemDataRole.UserRole, {"os_id": e.get("os_id"), "numero": e.get("numero")}
            )
            if e.get("atrasada"):
                # Cor NÃO é o único indicador: o texto já traz "⚠" e "atrasada"
                # (quick-reference §1 `color-not-only`, §2 `error-feedback`).
                linha.setData(Qt.ItemDataRole.ForegroundRole, _COR_ATRASO)
            self._lista_entregas.addItem(linha)

    @staticmethod
    def _texto_entrega(e: dict) -> str:
        cliente = e.get("cliente_nome") or "—"
        servico = e.get("servico") or "—"
        prazo = str(e.get("prazo") or "")[:10]
        status = str(e.get("status") or "").upper()
        if e.get("atrasada"):
            return f"⚠ Atrasada · {cliente} · {servico} · {prazo} · {status}"
        return f"{cliente} · {servico} · {prazo} · {status}"

    def _preencher_faturamento(self, realizado, previsto) -> None:
        """Um gráfico único (P0#2/#3): faixa de dias com realizado à esquerda,
        divisor "hoje", previsto à direita — substitui as duas séries empilhadas.

        Cada coluna tem rótulo centralizado; barras carregam série+valor no
        tooltip/acessibilidade; dias zerados ficam apoiados na linha de base.
        """
        container = self._container_barras
        # Na primeira carga não há layout: cria; nas recargas, limpa as colunas
        # antigas sem recriar o layout (QHBoxLayout não pode ser substituído).
        if container.layout() is None:
            QHBoxLayout(container)
        while container.layout().count():
            item = container.layout().takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        hoje = datetime.now().date()
        colunas: dict[str, dict[str, int]] = {}
        for v in realizado if isinstance(realizado, list) else []:
            if isinstance(v, dict):
                colunas.setdefault(self._chave_dia(v.get("data")), {})[
                    "barraRealizado"
                ] = self._num(v.get("valor"))
        for v in previsto if isinstance(previsto, list) else []:
            if isinstance(v, dict):
                colunas.setdefault(self._chave_dia(v.get("data")), {})[
                    "barraPrevisto"
                ] = self._num(v.get("valor"))

        vazio = not colunas or all(
            not valores or max(valores.values()) == 0 for valores in colunas.values()
        )
        self._lbl_grafico.setText(
            f"Sem vendas nos últimos {self._dias} dias." if vazio else ""
        )
        self._lbl_grafico.setVisible(bool(vazio))
        if vazio:
            return

        maior = max(
            max(valores.values()) for valores in colunas.values() if valores
        )
        linha = container.layout()
        for chave in sorted(colunas):
            valores = colunas[chave]
            dia_txt = self._dia_curto(chave)
            coluna = QVBoxLayout()
            coluna.setContentsMargins(0, 0, 0, 0)
            coluna.setSpacing(2)
            coluna.addWidget(self._barra_serie(valores, dia_txt, maior), 1)
            dia = QLabel(dia_txt)
            estado_muted(dia)
            dia.setAlignment(Qt.AlignmentFlag.AlignCenter)
            coluna.addWidget(dia)
            caixa = QWidget()
            caixa.setLayout(coluna)
            linha.addWidget(caixa, 1)
            # Divisor "hoje": termina a faixa de realizado, começa a prevista.
            if chave == self._chave_dia(hoje.isoformat()):
                divisor = QFrame()
                divisor.setFrameShape(QFrame.Shape.VLine)
                divisor.setObjectName("divisorHojeGrafico")
                linha.addWidget(divisor)

    def _barra_serie(self, valores: dict[str, int], dia_txt: str, maior: int) -> QWidget:
        """Par de barras (Realizado | Previsto) de um dia, empilhadas numa célula."""
        par = QHBoxLayout()
        par.setContentsMargins(0, 0, 0, 0)
        par.setSpacing(2)
        for marca, rotulo in (
            ("barraRealizado", "Realizado"),
            ("barraPrevisto", "Previsto"),
        ):
            barra = QProgressBar()
            barra.setObjectName(marca)
            barra.setOrientation(Qt.Orientation.Vertical)
            barra.setTextVisible(False)
            barra.setRange(0, max(1, int(maior)))
            barra.setValue(valores.get(marca, 0))
            valor_txt = self._moeda(valores.get(marca, 0))
            barra.setAccessibleName(f"{rotulo} {dia_txt}: {valor_txt}")
            barra.setToolTip(f"{rotulo} · {dia_txt} · {valor_txt}")
            par.addWidget(barra, 1)
            if marca not in valores:
                barra.setVisible(False)  # dia só de uma série (passado/futuro)
        celula = QWidget()
        celula.setLayout(par)
        return celula

    @staticmethod
    def _chave_dia(data) -> str:
        return str(data or "")[:10]

    def _aplicar_pendencias(self, dados) -> None:
        """Bloco "O que preciso fazer agora" (P1#6): só o que tem ação."""
        if not hasattr(self, "_lista_pendencias"):
            return
        self._lista_pendencias.clear()
        p = dados if isinstance(dados, dict) else {}
        linhas: list[tuple[str, str]] = []

        if self._int(p.get("caixa_aberto")) == 0 and p.get("caixa_aberto") is not None:
            linhas.append(("Caixa fechado — abra para registrar vendas", "financeiro"))
        saldo = p.get("caixa_saldo")
        if p.get("caixa_aberto"):
            linhas.append(
                (f"Caixa aberto · saldo {self._moeda(saldo)}", "financeiro")
            )
        n = self._int(p.get("orcamentos_aguardando_aprovacao"))
        if n:
            linhas.append(
                (self._plural(n, "orçamento aguardando aprovação", "orçamentos aguardando aprovação"), "os")
            )
        n = self._int(p.get("artes_aguardando_cliente"))
        if n:
            linhas.append(
                (self._plural(n, "arte aguardando o cliente", "artes aguardando o cliente"), "os")
            )
        n = self._int(p.get("os_prontas_retirada"))
        if n:
            linhas.append(
                (self._plural(n, "O.S. pronta para retirada", "O.S. prontas para retirada"), "os")
            )
        pagar = p.get("contas_pagar_hoje")
        if pagar is not None and self._num(pagar) > 0:
            linhas.append((f"Contas a pagar hoje: {self._moeda(pagar)}", "financeiro"))
        n = self._int(p.get("nfce_rejeitadas"))
        if n:
            linhas.append(
                (self._plural(n, "NFC-e rejeitada — reemitir", "NFC-e rejeitadas — reemitir"), "fiscal")
            )

        if not linhas:
            self._lista_pendencias.setVisible(False)
            self._vazio_pendencias.setVisible(True)
            return
        self._vazio_pendencias.setVisible(False)
        self._lista_pendencias.setVisible(True)
        for texto, destino in linhas:
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, destino)
            self._lista_pendencias.addItem(item)

    def _abrir_pendencia(self, item: QListWidgetItem) -> None:
        destino = item.data(Qt.ItemDataRole.UserRole)
        if destino:
            self.navegar.emit(destino)

    def _status_conexao(self, conectado: bool) -> None:
        if conectado or self._modo_leitura:
            self._alerta_conexao.setVisible(False)
        else:
            self._alerta_conexao.setText(
                "Servidor local sem resposta — verifique se o serviço está em execução."
            )
            self._alerta_conexao.setVisible(True)
        self.conexao_verificada.emit(conectado)

    def _sem_status(self, msg: str) -> None:
        self._alerta_conexao.setText(f"Servidor local indisponível: {msg}")
        self._alerta_conexao.setVisible(True)
        self.conexao_verificada.emit(False)

    def _sem_resumo(self, msg) -> None:
        self._resumo_recebido = True
        for skeleton in self._skeletons:
            skeleton.ocultar()
        # Falha ≠ zero real: valores saem da tela e entra o convite a retry
        # (revisão de telas P0#1) — nunca "R$ 0,00" sem dado.
        self._lbl_atualizado.setText("")
        self._btn_retry_resumo.setVisible(True)
        self._btn_retry_resumo.setToolTip(f"Motivo: {msg}")
        self._kpi_vendas_valor.setText("—")
        self._kpi_vendas_sub.setText("")
        if _eh_gerente_ou_mais(self._nivel):
            self._kpi_receber_valor.setText("—")
            self._kpi_receber_sub.setText("")
            self._kpi_pagar_valor.setText("—")
            self._kpi_pagar_sub.setText("")
            self._lbl_grafico.setText(
                "Não foi possível carregar o faturamento. Verifique o servidor local."
            )
            self._lbl_grafico.setVisible(True)
        if _eh_operador_ou_mais(self._nivel):
            self._kpi_projetos_valor.setText("—")
            self._kpi_projetos_sub.setText("")
            self._lbl_estoque.setText("Resumo de estoque indisponível no momento.")
            estado_muted(self._lbl_estoque)
            self._lbl_estoque.setAccessibleName(self._lbl_estoque.text())
            self._btn_estoque.setVisible(False)
            self._aplicar_entregas([])

    # -------------------------------------------------------------- helpers

    @staticmethod
    def _int(v) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _plural(n: int, singular: str, plural: str) -> str:
        return f"{n} {singular if n == 1 else plural}"

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

    def _cartao_kpi(
        self, titulo: str, valor: QLabel, sub: QLabel, destino: str | None = None
    ) -> QWidget:
        cartao = CartaoClique()
        cartao.setObjectName("cardLow")
        # Largura total da linha (stretch no layout do chamador) — sem mínimo
        # fixo que deixava a linha vazia em telas largas (P1#7).
        cartao.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(cartao)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        nome = ElideLabel(titulo)
        nome.setProperty("role", "muted")
        valor.setObjectName("valorCard")
        # O cartão inteiro é um grupo semântico: o leitor de tela lê
        # "título · valor · subtexto" numa passada, sem depender da cor ou da
        # posição visual (quick-reference §1 `voiceover-sr`, `color-not-only`).
        cartao.setAccessibleName(titulo)
        valor.setAccessibleName(f"{titulo}: valor")
        sub.setAccessibleName(f"{titulo}: detalhe")
        sub.setProperty("role", "muted")
        layout.addWidget(nome)
        layout.addWidget(valor)
        layout.addWidget(sub)
        if destino:
            # KPI clicável: abre o módulo do detalhe (P1#7).
            cartao.setToolTip(f"Abrir {titulo.lower()}")
            cartao.clicado.connect(lambda d=destino: self.navegar.emit(d))
        # Skeleton do primeiro carregamento: barras no lugar de valor/sub até o
        # resumo chegar (`mostrar()`/`ocultar()` em `_carregar_resumo`).
        self._skeletons.append(SkeletonCartao(cartao))
        return cartao


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
        # Colapso automático por largura (P0#2 da revisão do PDV): 0 = manual.
        self._colapso_automatico = False
        self._detalhe_licenca = "Licença ainda não verificada."

        self.setWindowTitle(APP_NAME)
        # Matriz de resoluções suportadas: 1024x768 (mínimo) e 1366x768.
        # O mínimo é 1024x768 — abaixo disso o layout não é garantido.
        # Em 1366 a janela abre maximizada (main.py) com sidebar expandida,
        # rótulos completos e espaçamentos normais; em 1024 o resizeEvent
        # colapsa a sidebar, elide rótulos e comprime espaçamentos.
        self.setMinimumSize(1024, 768)

        raiz = QWidget()
        coluna = QVBoxLayout(raiz)
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        self._coluna_raiz = coluna
        self._banner_atualizacao: NotificacaoAtualizacao | None = None

        if modo_leitura:
            coluna.addWidget(self._banner_modo_leitura())

        # Banner não bloqueante do estado `tolerancia` (doc de integração §9.3):
        # fica oculto por padrão e o layout ignora widget oculto.
        self._banner_tol = self._banner_tolerancia()
        coluna.addWidget(self._banner_tol)

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

        # Última situação conhecida da licença (o banner de tolerância e o
        # indicador vivem dela mesmo quando o daemon local não responde).
        self._situacao_licenca: dict = {}

        # Countdown do banner: recompõe o texto/dia a cada minuto, sem rede — a
        # situação é reconsultada pelo `_timer_licenca_refresh` (5 min).
        self._timer_tolerancia = QTimer(self)
        self._timer_tolerancia.setInterval(60 * 1000)
        self._timer_tolerancia.timeout.connect(self._atualizar_tolerancia)

        if situacao_licenca is not None:
            # Licença já consultada no login (token de sessão): evita o 2º GET.
            self._licenca(situacao_licenca)
        else:
            self._timer_licenca = QTimer(self)
            self._timer_licenca.setSingleShot(True)
            self._timer_licenca.setInterval(0)
            self._timer_licenca.timeout.connect(self._carregar_licenca)
            self._timer_licenca.start()

        # Repinta o indicador a cada 5 min: o estado pode mudar em background
        # (ativa → tolerância → leitura) sem o usuário reabrir a tela.
        self._timer_licenca_refresh = QTimer(self)
        self._timer_licenca_refresh.setInterval(5 * 60 * 1000)
        self._timer_licenca_refresh.timeout.connect(self._carregar_licenca)
        self._timer_licenca_refresh.start()

        # Aviso de versão: checagem assíncrona logo após o dashboard aparecer.
        # Nunca bloqueia login/licença — falha de rede só vai para o log.
        self._timer_atualizacao = QTimer(self)
        self._timer_atualizacao.setSingleShot(True)
        self._timer_atualizacao.setInterval(2000)
        self._timer_atualizacao.timeout.connect(self._verificar_atualizacao)
        self._timer_atualizacao.start()

    # ------------------------------------------------------- atualização

    def _verificar_atualizacao(self) -> None:
        from printgest.core import atualizacao

        rodar(
            lambda: atualizacao.verificar(__version__),
            on_ok=self._mostrar_atualizacao,
            on_erro=lambda _msg: None,
        )

    def _mostrar_atualizacao(self, informacoes: dict | None) -> None:
        if not informacoes or self._banner_atualizacao is not None:
            return
        banner = NotificacaoAtualizacao(informacoes, self)
        banner.atualizar_solicitado.connect(self._abrir_release)
        self._banner_atualizacao = banner
        self._coluna_raiz.insertWidget(0, banner)

    @staticmethod
    def _abrir_release(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # -------------------------------------------------------------- topo

    def _cabecalho(self) -> QWidget:
        cabecalho = QWidget()
        cabecalho.setObjectName("cabecalho")
        self._cabecalho_widget = cabecalho
        linha = QHBoxLayout(cabecalho)
        linha.setContentsMargins(20, 10, 20, 10)
        linha.setSpacing(12)

        # P3 (1024px): rótulos do topo elidem (com tooltip) em vez de impor
        # largura mínima — o cabeçalho travava a janela em ~1248px.
        marca = ElideLabel(APP_NAME)
        marca.setObjectName("marca")
        marca.setMinimumWidth(130)
        linha.addWidget(marca)

        self._lbl_filial = ElideLabel(self._usuario.get("filial_nome", ""))
        estado_muted(self._lbl_filial)
        linha.addWidget(self._lbl_filial)

        # Indicador do servidor local — estado legível ("online"/"offline"),
        # IP fica só no tooltip (duplicava com o rodapé; revisão P0#4/P2#14).
        server_ip = self._base_url.split(":")[0] if ":" in self._base_url else self._base_url
        self._lbl_servidor = ElideLabel("● verificando…")
        estado_muted(self._lbl_servidor)
        self._lbl_servidor.setToolTip(f"Servidor local: {self._base_url}")
        linha.addWidget(self._lbl_servidor)
        linha.addStretch(1)

        self._busca = BuscaGlobal(self._api, self._nivel)
        self._busca.navegar.connect(self._navegar)
        self._busca.abrir_registro.connect(self._abrir_registro)
        # Caixa não pode abrir clientes/produtos/O.S.: esconder o campo evita
        # uma busca que nunca retorna nada (antes ficava visível e morto).
        self._entidades_busca = [
            entidade for entidade, modulo in MODULO_POR_ENTIDADE.items()
            if pode_abrir(self._nivel, modulo)
        ]
        self._busca.setVisible(bool(self._entidades_busca))
        if self._entidades_busca:
            self._busca.setToolTip(
                "Buscar " + ", ".join(self._entidades_busca)
            )
        linha.addWidget(self._busca)

        self._btn_alertas = QPushButton("🔔")
        self._btn_alertas.setProperty("icone", "true")
        self._btn_alertas.setToolTip("Central de alertas")
        self._btn_alertas.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_alertas.clicked.connect(self._abrir_alertas)
        linha.addWidget(self._btn_alertas)

        self._btn_prefs = QPushButton("⚙")
        self._btn_prefs.setProperty("icone", "true")
        self._btn_prefs.setToolTip("Preferências")
        self._btn_prefs.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prefs.clicked.connect(self._abrir_preferencias)
        linha.addWidget(self._btn_prefs)

        self._lbl_licenca = QPushButton("● Licença")
        estado_atencao(self._lbl_licenca)
        self._lbl_licenca.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lbl_licenca.setToolTip("Situação da licença")
        self._lbl_licenca.clicked.connect(self._abrir_licenca)
        linha.addWidget(self._lbl_licenca)

        nome = self._usuario.get("nome") or self._usuario.get("login", "?")
        perfil = _PERFIL_CURTO.get(self._nivel, self._nivel)
        self._menu_usuario = QToolButton()
        self._menu_usuario.setObjectName("menuUsuario")
        # Quando nome e perfil são o mesmo conceito (ex.: "Administrador"/"Admin",
        # "Caixa"/"Caixa"), mostra só um — evita repetir a mesma palavra (spec C6).
        texto_menu = f"{self._iniciais(nome)}  {nome}"
        nome_norm = nome.strip().casefold()
        perfil_norm = perfil.strip().casefold()
        repetido = bool(nome_norm) and bool(perfil_norm) and (
            nome_norm.startswith(perfil_norm)
            or perfil_norm.startswith(nome_norm)
        )
        if not repetido:
            texto_menu += f"  · {perfil}"
        self._menu_usuario.setText(texto_menu)
        self._menu_usuario.setToolTip(f"{nome} — {nivel_rotulo(self._nivel)}")
        self._menu_usuario.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_usuario.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._menu_usuario)
        menu.addAction("Preferências", self._abrir_preferencias)
        menu.addAction("Trocar senha", self._abrir_trocar_senha)
        menu.addAction("Verificar atualização", self._verificar_atualizacao)
        menu.addSeparator()
        menu.addAction("Sair", self._sair)
        self._menu_usuario.setMenu(menu)
        linha.addWidget(self._menu_usuario)
        return cabecalho

    @staticmethod
    def _iniciais(nome: str) -> str:
        partes = [p for p in str(nome).split() if p]
        if not partes:
            return "?"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[-1][0]).upper()

    def _abrir_alertas(self) -> None:
        menu = QMenu(self)
        menu.addAction("Nenhum alerta no momento").setEnabled(False)
        menu.exec(
            self._btn_alertas.mapToGlobal(self._btn_alertas.rect().bottomLeft())
        )

    def _abrir_preferencias(self) -> None:
        alvo = "personalizacao" if pode_abrir(self._nivel, "personalizacao") else "configuracoes"
        if pode_abrir(self._nivel, alvo):
            self._navegar(alvo)

    def _abrir_trocar_senha(self) -> None:
        if pode_abrir(self._nivel, "usuarios"):
            self._navegar("usuarios")
        else:
            QMessageBox.information(
                self,
                "Trocar senha",
                "Solicite ao administrador a alteração da sua senha.",
            )

    def _abrir_licenca(self) -> None:
        QMessageBox.information(self, "Licença", self._detalhe_licenca)

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
        self._pintar_licenca(sit)

    def _sem_licenca(self, msg) -> None:
        self._pintar_licenca({})

    def _pintar_licenca(self, sit: dict) -> None:
        if sit:
            # Guarda a última situação conhecida: se o daemon local não responder,
            # o indicador e o banner de tolerância não "somem" da tela.
            self._situacao_licenca = sit
        self._detalhe_licenca = self._detalhe_texto(sit, self._modo_leitura)
        self._lbl_licenca.setText(self._texto_indicador_licenca(sit, self._modo_leitura))
        self._lbl_licenca.setProperty(
            "role", self._estilo_licenca(sit, self._modo_leitura)
        )
        self._lbl_licenca.setToolTip(self._detalhe_licenca)
        aplicar_estilo(self._lbl_licenca)
        self._atualizar_tolerancia()

    @staticmethod
    def _texto_indicador_licenca(sit: dict, modo_leitura: bool) -> str:
        """Texto do indicador com informação, não só um ponto (P0#4).

        Estado + prazo quando legível: "Licença · 29 d", "Tolerância", "Leitura".
        """
        if modo_leitura or sit.get("modo_leitura") or sit.get("estado") in (
            "leitura",
            "revogada",
        ):
            return "● Modo leitura"
        if sit.get("estado") == "tolerancia":
            restante = tempo_restante(sit.get("tolerancia_expira_em"))
            return f"● Tolerância{f' · {restante}' if restante else ''}"
        fim = _momento(sit.get("expira_em"))
        if fim is not None:
            dias = (fim - _agora_utc()).days
            if dias >= 0:
                return f"● Licença · {dias} d"
        if sit.get("status") == "ativa" or sit.get("estado") == "ativa":
            return "● Licença ativa"
        return "● Licença"

    def _atualizar_tolerancia(self) -> None:
        """Mostra/atualiza o banner de tolerância a partir da situação conhecida.

        Não chama a rede: é o callback do `QTimer` de 1 min (countdown) e também
        roda a cada repintura do indicador (5 min), com a situação recém-consultada.
        """
        sit = self._situacao_licenca
        visivel = not self._modo_leitura and sit.get("estado") == "tolerancia"
        self._banner_tol.setVisible(visivel)
        if not visivel:
            self._timer_tolerancia.stop()
            return

        self._lbl_tol.setText(mensagem_tolerancia(sit))
        restante = tempo_restante(sit.get("tolerancia_expira_em"))
        self._lbl_tol_restante.setText(
            f"Restam {restante}" if restante else "Tolerância ativa"
        )
        self._lbl_tol_restante.setToolTip(
            "O sistema opera normalmente enquanto o servidor de licenças estiver "
            "inacessível; ao fim do prazo, entra em modo leitura."
        )
        fracao = fracao_tolerancia(sit)
        self._barra_tol.setVisible(fracao is not None)
        if fracao is not None:
            self._barra_tol.setValue(int(round(fracao * 1000)))
        if not self._timer_tolerancia.isActive():
            self._timer_tolerancia.start()

    @staticmethod
    def _texto_licenca(sit: dict, modo_leitura: bool) -> str:
        estado = sit.get("estado")
        if estado == "tolerancia":
            return "Licença em tolerância"
        if estado == "revogada":
            return "Licença revogada"
        if estado == "leitura" or modo_leitura:
            return "Modo Leitura"
        if estado == "ativa" or sit.get("status") == "ativa":
            return "Licença Ativa"
        if sit.get("status"):
            return "Licença pendente"
        return "Verificando licença..."

    @staticmethod
    def _estilo_licenca(sit: dict, modo_leitura: bool) -> str:
        estado = sit.get("estado")
        if modo_leitura or sit.get("modo_leitura") or estado in ("leitura", "revogada"):
            return "erro"
        if estado == "tolerancia":
            # Sem contato com o RedGest, mas dentro da janela: alerta, não bloqueio.
            return "atencao"
        if estado == "ativa" or sit.get("status") == "ativa":
            return "success"
        return "atencao"

    @staticmethod
    def _detalhe_texto(sit: dict, modo_leitura: bool) -> str:
        """Mensagem completa (P21): estado + motivo + prazos + último erro."""
        linhas = [f"{TelaPrincipal._texto_licenca(sit, modo_leitura)}."]
        if sit.get("motivo"):
            linhas.append(str(sit["motivo"]))
        if sit.get("plano"):
            linhas.append(f"Plano: {sit['plano']}")
        if sit.get("chave"):
            linhas.append(f"Chave: {sit['chave']}")
        if sit.get("limite_ativacoes"):
            linhas.append(
                f"Estações autorizadas: {sit['limite_ativacoes']} "
                f"(em uso: {sit.get('ativacoes_realizadas') or 0})"
            )
        if formatar_datahora(sit.get("expira_em")):
            linhas.append(f"Válida até: {formatar_datahora(sit['expira_em'])}")
        if sit.get("estado") == "tolerancia":
            linhas.append(
                f"Tolerância até: {formatar_datahora(sit.get('tolerancia_expira_em'))}"
            )
        if formatar_datahora(sit.get("ultima_tentativa_em")):
            linhas.append(
                f"Última verificação: {formatar_datahora(sit['ultima_tentativa_em'])}"
            )
        if sit.get("ultimo_erro"):
            linhas.append(f"Último erro: {sit['ultimo_erro']}")
        return "\n".join(linhas)

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

    def _banner_tolerancia(self) -> QWidget:
        """Banner **não bloqueante** do estado `tolerancia` (doc de integração §9.3).

        Informa em quanto tempo a licença deixa de valer (tolerância de 72 h da
        vigência) sem travar nada: as escritas seguem liberadas. O texto e a
        barra são recompostos por `_atualizar_tolerancia`.
        """
        banner = QWidget()
        banner.setObjectName("bannerAmber")
        linha = QHBoxLayout(banner)
        linha.setContentsMargins(24, 8, 24, 8)
        linha.setSpacing(10)

        self._lbl_tol = QLabel("")
        self._lbl_tol.setStyleSheet("font-weight: 600; font-size: 13px;")
        linha.addWidget(self._lbl_tol)

        self._lbl_tol_restante = QLabel("")
        estado_atencao(self._lbl_tol_restante)
        linha.addWidget(self._lbl_tol_restante)

        self._barra_tol = QProgressBar()
        self._barra_tol.setObjectName("barraTolerancia")
        self._barra_tol.setTextVisible(False)
        self._barra_tol.setRange(0, 1000)
        self._barra_tol.setFixedWidth(160)
        self._barra_tol.setFixedHeight(6)
        linha.addWidget(self._barra_tol)

        linha.addStretch(1)
        banner.setVisible(False)
        return banner

    def _barra_lateral(self) -> QWidget:
        lateral = QWidget()
        lateral.setObjectName("sidebar")
        lateral.setFixedWidth(224)
        layout = QVBoxLayout(lateral)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(2)

        self._btn_colapso = self._botao_menu("«", checkavel=False)
        self._btn_colapso.setToolTip("Recolher menu")
        self._btn_colapso.setAccessibleName("Recolher menu")
        self._btn_colapso.clicked.connect(self._alternar_colapso)
        layout.addWidget(self._btn_colapso)

        inicio = self._botao_menu("Início", checkavel=True)
        inicio.setChecked(True)
        inicio.setToolTip("Início")
        inicio.setAccessibleName("Início")
        inicio.clicked.connect(lambda: self._navegar(ITEM_INICIO))
        layout.addWidget(inicio)
        self._btn_menu = {ITEM_INICIO: inicio}
        self._rotulo_por_id = {ITEM_INICIO: "Início"}
        self._itens_lateral: list[QWidget] = []
        self._grupos_menu: list[QLabel] = []
        self._botoes_menu: list[QPushButton] = [inicio]

        # A lista fica dentro de um QScrollArea: em 1366×768 o menu do ADMIN
        # pede ~747 px contra ~688 px úteis — sem rolagem o grupo SISTEMA
        # ficava cortado. O scroll não cresce a janela (política Ignored).
        rolagem = QScrollArea()
        rolagem.setObjectName("menuScroll")
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.Shape.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        rolagem.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        rolagem.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored
        )
        conteudo = QWidget()
        conteudo.setObjectName("menuConteudo")
        lista = QVBoxLayout(conteudo)
        lista.setContentsMargins(0, 0, 0, 0)
        lista.setSpacing(2)

        for grupo, itens in menu_visivel(self._nivel):
            rotulo = QLabel(grupo.upper())
            rotulo.setObjectName("grupoMenu")
            lista.addWidget(rotulo)
            self._itens_lateral.append(rotulo)
            self._grupos_menu.append(rotulo)
            for item in itens:
                botao = self._botao_menu(item["rotulo"])
                botao.setToolTip(item["rotulo"])
                botao.setAccessibleName(item["rotulo"])
                botao.clicked.connect(
                    lambda _=False, i=item["id"]: self._navegar(i)
                )
                self._btn_menu[item["id"]] = botao
                self._rotulo_por_id[item["id"]] = item["rotulo"]
                self._botoes_menu.append(botao)
                self._itens_lateral.append(botao)
                lista.addWidget(botao)

        lista.addStretch(1)
        rolagem.setWidget(conteudo)
        layout.addWidget(rolagem, 1)

        # As ações de criação ("Nova venda"/"Nova OS/Orçamento") vivem apenas no
        # "Acesso rápido" do Início — evita duplicar ações com rótulos diferentes.
        return lateral

    def resizeEvent(self, evento) -> None:  # noqa: N802 (API do Qt)
        super().resizeEvent(evento)
        # P3 (1024px): em janelas estreitas, esconde os indicadores secundários
        # do topo (filial/servidor) para preservar marca, busca, licença e
        # usuário. O estado completo continua em tooltips/rodapé.
        if hasattr(self, "_lbl_filial"):
            self._lbl_filial.setVisible(self.width() >= 1180)
        if hasattr(self, "_lbl_servidor"):
            self._lbl_servidor.setVisible(self.width() >= 1120)
        # Comprime os espaçamentos do topo/rodapé para caber em 1024px sem
        # cortar texto (os rótulos já elidem e mantêm tooltip).
        denso = self.width() < 1200
        if hasattr(self, "_cabecalho_widget"):
            lay = self._cabecalho_widget.layout()
            lay.setSpacing(6 if denso else 12)
            lay.setContentsMargins(12 if denso else 20, 10, 12 if denso else 20, 10)
        if hasattr(self, "_rodape_widget"):
            lay = self._rodape_widget.layout()
            lay.setSpacing(8 if denso else 14)
            lay.setContentsMargins(12 if denso else 16, 6, 12 if denso else 16, 6)
        # P0#2 (revisão PDV): abaixo de ~1280 px o layout de duas colunas do
        # PDV não cabe — a sidebar recolhe automaticamente para o trilho de 64
        # px. O toque manual do operador vence (só re-automatiza ao voltar da
        # largura estreita para a larga depois de um colapso automático).
        estreita = self.width() < 1280
        if estreita and not self._colapsada:
            self._colapso_automatico = True
            self._alternar_colapso()
        elif not estreita and self._colapsada and self._colapso_automatico:
            self._colapso_automatico = False
            self._alternar_colapso()

    def _alternar_colapso(self) -> None:
        """Colapsa/expande a barra lateral com largura animada (§4, §5).

        A largura parte do valor **atual** em tela (interrompível: clicar de novo
        no meio reverte sem salto). Sem movimento habilitado — SO pedindo menos
        movimento ou plataforma offscreen — aplica o estado final de imediato.
        """
        self._colapsada = not self._colapsada
        if not self._colapsada:
            self._colapso_automatico = False
        largura_final = 64 if self._colapsada else 224
        self._btn_colapso.setText("»" if self._colapsada else "«")
        self._aplicar_rotulos_menu(self._colapsada)

        if not animacao.animacoes_habilitadas():
            self._sidebar.setFixedWidth(largura_final)
            aplicar_estilo(self._sidebar)
            return

        animacao.animar_largura(
            self._sidebar,
            self._sidebar.width(),
            largura_final,
            ao_fim=lambda: aplicar_estilo(self._sidebar),
        )

    def _aplicar_rotulos_menu(self, colapsada: bool) -> None:
        """Trilho colapsado mantém TODOS os links clicáveis, só encurta o texto."""
        for item_id, botao in self._btn_menu.items():
            botao.setText(
                _rotulo_curto(item_id, self._rotulo_por_id[item_id])
                if colapsada else self._rotulo_por_id[item_id]
            )
        for grupo in self._grupos_menu:
            grupo.setVisible(not colapsada)
        for botao in self._botoes_menu:
            botao.setVisible(True)
        dica = "Expandir menu" if colapsada else "Recolher menu"
        self._btn_colapso.setToolTip(dica)
        self._btn_colapso.setAccessibleName(dica)

    def _botao_menu(self, texto: str, checkavel: bool = True) -> QPushButton:
        botao = QPushButton(texto)
        botao.setProperty("nav", "true")
        botao.setCheckable(checkavel)
        botao.setCursor(Qt.CursorShape.PointingHandCursor)
        return botao

    def _stack(self) -> QStackedWidget:
        # P3: pilha responsiva — páginas largas (PDV/Histórico) não forçam a
        # janela a crescer além da resolução do operador.
        self._stack_paginas = PilhaResponsiva()
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
        self._lbl_filial.setToolTip("Unidade em uso (matriz ou filial)")

    def _rodape(self) -> QWidget:
        rodape = QWidget()
        rodape.setObjectName("rodape")
        self._rodape_widget = rodape
        linha = QHBoxLayout(rodape)
        linha.setContentsMargins(16, 6, 16, 6)
        linha.setSpacing(14)

        # P3 (1024px): todo o rodapé usa rótulos elidíveis — antes os oito
        # QLabels fixavam ~1248px de largura mínima e impediam 1024×768.
        self._lbl_relogio = ElideLabel(datetime.now().strftime("%H:%M:%S"))
        self._lbl_relogio.setMinimumWidth(78)
        estado_muted(self._lbl_relogio)
        linha.addWidget(self._lbl_relogio)
        self._timer_relogio = QTimer(self)
        self._timer_relogio.setInterval(1000)
        self._timer_relogio.timeout.connect(self._tick_relogio)
        self._timer_relogio.start()

        host = ElideLabel(socket.gethostname())
        host.setToolTip(f"Estação: {socket.gethostname()}")
        estado_muted(host)
        linha.addWidget(host)

        # Servidor: IP/Porta do servidor (extraído de base_url)
        server_ip = self._base_url.split(":")[0] if ":" in self._base_url else self._base_url
        server_label = ElideLabel(f"  · Servidor: {server_ip}")
        server_label.setToolTip(f"Servidor local: {self._base_url}")
        estado_muted(server_label)
        linha.addWidget(server_label)

        self._lbl_conexao = ElideLabel("● —")
        estado_muted(self._lbl_conexao)
        linha.addWidget(self._lbl_conexao)
        # A Tela Início já consulta /health ao abrir; o rodapé reaproveita o
        # resultado em vez de disparar uma 2ª chamada no arranque.
        self._pagina_inicio.conexao_verificada.connect(self._pintar_conexao)

        for kbd, texto, modulo in [
            ("F2", "Clientes", "cliente"),
            ("F3", "Produtos", "produto"),
            ("F5", "PDV", "pdv"),
        ]:
            # Não anunciar atalho que este perfil não pode executar (caixa).
            if not pode_abrir(self._nivel, modulo):
                continue
            hint = ElideLabel(f"[{kbd}] {texto}")
            hint.setToolTip(f"{texto} ({kbd})")
            estado_muted(hint)
            linha.addWidget(hint)
        linha.addStretch(1)
        versao = ElideLabel(f"v{__version__}")
        versao.setToolTip(f"PrintGest ERP v{__version__}")
        estado_muted(versao)
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
        # Estado legível no cabeçalho E no rodapé (P0#4): o ponto verde/vermelho
        # vem com a palavra, e o IP fica no tooltip do cabeçalho.
        self._lbl_conexao.setText("● online" if ok else "○ offline")
        self._lbl_servidor.setText("● online" if ok else "○ offline")
        if ok:
            estado_sucesso(self._lbl_conexao)
            estado_sucesso(self._lbl_servidor)
        else:
            estado_erro(self._lbl_conexao)
            estado_erro(self._lbl_servidor)

    # ------------------------------------------------------------ navegação

    def _instalar_atalhos(self) -> None:
        atalhos = {"F2": "cliente", "F3": "produto", "F5": "pdv"}
        for tecla, item_id in atalhos.items():
            if not pode_abrir(self._nivel, item_id):
                continue
            atalho = QShortcut(QKeySequence(tecla), self)
            atalho.activated.connect(lambda i=item_id: self._navegar(i))

    def _abrir_registro(self, registro_id: str) -> None:
        """BuscaGlobal: abrir a sugestão no módulo de destino."""
        try:
            alvo = int(registro_id)
        except (TypeError, ValueError):
            return
        pagina = getattr(self, "_pagina_atual_id", None)
        tabela = getattr(self._paginas.get(pagina), "_tabela", None) if pagina else None
        if tabela is not None and hasattr(tabela, "selecionar_id"):
            tabela.selecionar_id(alvo)

    def _navegar(self, item_id: str) -> None:
        if item_id != ITEM_INICIO and not pode_abrir(self._nivel, item_id):
            return
        if item_id == ITEM_INICIO:
            # Dashboard: recarrega KPIs ao voltar (antes ficava parado a sessão
            # inteira — só atualizava no construtor, troca de dias ou retry).
            if hasattr(self._pagina_inicio, "recarregar"):
                self._pagina_inicio.recarregar()
            self._pagina_atual_id = ITEM_INICIO
            self._marcar(ITEM_INICIO)
            self._stack_paginas.setCurrentWidget(self._pagina_inicio)
            self.navegado.emit(ITEM_INICIO)
            return

        pagina = self._paginas.get(item_id)
        if pagina is None:
            rotulo = rotulo_do_item(item_id)
            pagina = criar_pagina(
                item_id, rotulo, self._api, self._modo_leitura, self._nivel
            )
            self._paginas[item_id] = pagina
            self._stack_paginas.addWidget(pagina)
            # Páginas que pedem para abrir outro módulo (ex.: PDV → Nova OS).
            if hasattr(pagina, "navegar"):
                pagina.navegar.connect(self._navegar)
        # Páginas reaproveitadas: recarrega ao reentrar para refletir escritas
        # feitas em outros módulos (ex.: venda lançada no caixa, cadastro
        # alterado em outra tela). Executa em background — nunca bloqueia.
        if hasattr(pagina, "recarregar"):
            pagina.recarregar()
        self._pagina_atual_id = item_id
        self._marcar(item_id)
        self._stack_paginas.setCurrentWidget(pagina)
        # A página "materializa" com um fade curto (§12): responder na hora,
        # nunca bloquear o input (§1). O fade parte da opacidade atual.
        animacao.aparecer(pagina)
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