"""Telas de plataforma do PRD v3.3: Filiais, Estações, Diagnóstico e Backup.

Todas Admin-only. Nenhuma tela mostra segredo: o diagnóstico usa os dados já
sanitizados pelo backend e o backup exige aceite do termo LGPD antes do
espelho no Neon.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import printgest.core.tarefas as tarefas
from printgest.core.api import Api
from printgest.ui.formulario import CampoCheck, CampoCombo, CampoTexto, em_volta
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import (
    ElideLabel,
    estado_atencao,
    estado_muted,
    estado_primario,
    estado_secundario,
    estado_sucesso,
)


def _quando(valor) -> str:
    if not valor:
        return "—"
    texto = str(valor).replace("T", " ")[:19]
    return texto


class _PaginaSimples(QWidget):
    """Base com título, subtítulo e corpo — padrão das telas de plataforma."""

    TITULO = ""
    SUBTITULO = ""

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)
        titulo = ElideLabel(self.TITULO)
        titulo.setObjectName("titulo")
        col.addWidget(titulo)
        if self.SUBTITULO:
            sub = QLabel(self.SUBTITULO)
            sub.setObjectName("subtitulo")
            sub.setWordWrap(True)
            col.addWidget(sub)
        self._corpo = QVBoxLayout()
        self._corpo.setContentsMargins(0, 0, 0, 0)
        self._corpo.setSpacing(8)
        col.addLayout(self._corpo, 1)

    def _erro(self, msg: str) -> None:
        QMessageBox.warning(self, self.TITULO, msg)


# ------------------------------------------------------------------- filiais


class PaginaFiliais(_PaginaSimples):
    TITULO = "Filiais"
    SUBTITULO = (
        "Cada filial tem um servidor (instalação) e um papel definidos pela "
        "licença. O papel MATRIZ é a origem dos cadastros mestres."
    )
    CHAVES = ["id", "nome", "papel", "instalacao_id", "ativa"]
    COLUNAS = ["#", "Filial", "Papel", "Instalação", "Ativa"]
    PESOS = [1, 5, 2, 4, 2]

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._tabela = TabelaDensa(self.CHAVES, self.COLUNAS, self.PESOS)
        self._tabela.formata = self._formatar
        self._corpo.addWidget(self._tabela, 1)
        linha = QHBoxLayout()
        self._btn_editar = QPushButton("Definir papel")
        estado_secundario(self._btn_editar)
        self._btn_editar.clicked.connect(self._editar)
        linha.addStretch(1)
        linha.addWidget(self._btn_editar)
        self._corpo.addLayout(linha)
        self._carregar()

    def _formatar(self, dado: dict, chave: str) -> str:
        if chave == "papel":
            return dado.get("papel") or "—"
        if chave == "instalacao_id":
            return dado.get("instalacao_id") or "—"
        if chave == "ativa":
            return "Sim" if dado.get("ativa") else "Não"
        return str(dado.get(chave) or "")

    def _carregar(self) -> None:
        def ok(lista) -> None:
            itens = lista if isinstance(lista, list) else lista.get("data", [])
            self._tabela.preencher(itens)

        tarefas.rodar(self._api.filiais, ok, self._erro)

    def _editar(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(self, "Filiais", "Selecione uma filial.")
            return
        if self._modo_leitura:
            return
        papel, ok = QInputDialog.getItem(
            self, "Papel da instalação", "Papel:", ["MATRIZ", "FILIAL"], 0, False
        )
        if not ok:
            return

        def salvo(_) -> None:
            self._carregar()

        tarefas.rodar(
            lambda: self._api.atualizar_filial(dado["id"], {"papel": papel}),
            salvo,
            self._erro,
        )


# ------------------------------------------------------------------ estações


class PaginaEstacoes(_PaginaSimples):
    TITULO = "Estações"
    SUBTITULO = (
        "Estação não é licenciada individualmente: o limite vale por servidor "
        "e só contam as que acessaram nos últimos 7 dias."
    )
    CHAVES = ["nome", "fingerprint", "ultimo_acesso", "dias_inativa"]
    COLUNAS = ["Estação", "Identificação", "Último acesso", "Dias inativa", "Situação"]
    PESOS = [4, 3, 4, 2, 2]

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._lbl = QLabel("")
        estado_muted(self._lbl)
        self._corpo.addWidget(self._lbl)
        self._tabela = TabelaDensa(self.CHAVES, self.COLUNAS, self.PESOS)
        self._tabela.formata = self._formatar
        self._corpo.addWidget(self._tabela, 1)
        linha = QHBoxLayout()
        self._btn_remover = QPushButton("Remover selecionada")
        estado_secundario(self._btn_remover)
        self._btn_remover.clicked.connect(self._remover)
        linha.addStretch(1)
        linha.addWidget(self._btn_remover)
        self._corpo.addLayout(linha)
        self._carregar()

    def _formatar(self, dado: dict, chave: str) -> str:
        if chave == "ultimo_acesso":
            return _quando(dado.get(chave))
        if chave == "dias_inativa":
            return str(dado.get(chave) or 0)
        return str(dado.get(chave) or "")

    def _carregar(self) -> None:
        def ok(saida: dict) -> None:
            self._tabela.preencher(saida.get("estacoes", []))
            self._lbl.setText(
                f"Estações ativas: {saida.get('total', 0)} de "
                f"{saida.get('limite', 0)} · vagas: {saida.get('vagas', 0)}"
            )
            estado_sucesso(self._lbl)

        tarefas.rodar(self._api.estacoes, ok, self._erro)

    def _remover(self) -> None:
        dado = self._tabela.objeto_selecionado()
        if not dado:
            QMessageBox.information(self, "Estações", "Selecione uma estação.")
            return
        if self._modo_leitura:
            return
        resp = QMessageBox.question(
            self, "Estações", f"Remover a estação {dado.get('nome')}?"
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        tarefas.rodar(
            lambda: self._api.remover_estacao(dado["id"]),
            lambda _: self._carregar(),
            self._erro,
        )


# --------------------------------------------------------------- diagnóstico


class PaginaDiagnostico(_PaginaSimples):
    TITULO = "Diagnóstico da licença"
    SUBTITULO = (
        "Dados para suporte. Nenhum segredo, código de licença ou token "
        "completo é exibido nem copiado."
    )

    CAMPOS = [
        ("estado", "Estado"),
        ("modo_leitura", "Modo leitura"),
        ("plano", "Plano"),
        ("status_servidor", "Status do servidor"),
        ("estado_vinculo", "Vínculo"),
        ("instalacao_nome", "Nome da instalação"),
        ("papel", "Papel"),
        ("max_estacoes", "Limite de estações"),
        ("max_filiais", "Limite de filiais"),
        ("modulos_habilitados", "Módulos habilitados"),
        ("ultima_renovacao_ok", "Última renovação OK"),
        ("ultima_tentativa_em", "Última tentativa"),
        ("falhas_seguidas", "Falhas seguidas"),
        ("versao", "Versão"),
    ]

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._lbl = QLabel("Carregando diagnóstico…")
        self._lbl.setWordWrap(True)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        estado_muted(self._lbl)
        self._corpo.addWidget(self._lbl, 1)
        linha = QHBoxLayout()
        self._btn_copiar = QPushButton("Copiar diagnóstico")
        estado_secundario(self._btn_copiar)
        self._btn_copiar.clicked.connect(self._copiar)
        atualizar = QPushButton("Atualizar")
        estado_primario(atualizar)
        atualizar.clicked.connect(self._carregar)
        linha.addStretch(1)
        linha.addWidget(self._btn_copiar)
        linha.addWidget(atualizar)
        self._corpo.addLayout(linha)
        self._dados: dict = {}
        self._carregar()

    def _carregar(self) -> None:
        def ok(resp: dict) -> None:
            self._dados = resp.get("data", resp) if isinstance(resp, dict) else {}
            linhas = []
            for chave, rotulo in self.CAMPOS:
                valor = self._dados.get(chave)
                if isinstance(valor, list):
                    valor = ", ".join(str(v) for v in valor) or "—"
                elif isinstance(valor, bool):
                    valor = "Sim" if valor else "Não"
                linhas.append(f"<b>{rotulo}:</b> {valor if valor not in (None, '') else '—'}")
            eventos = self._dados.get("eventos") or []
            if eventos:
                linhas.append("<b>Últimos eventos:</b>")
                for ev in eventos[:10]:
                    linhas.append(
                        f"&nbsp;&nbsp;• {_quando(ev.get('em'))} — {ev.get('tipo')}"
                        + (f" ({ev.get('codigo_erro')})" if ev.get("codigo_erro") else "")
                    )
            self._lbl.setText("<br>".join(linhas))

        tarefas.rodar(self._api.diagnostico_licenca, ok, self._erro)

    def _copiar(self) -> None:
        dados = self._dados or {}
        linhas = [f"{rotulo}: {dados.get(chave, '—')}" for chave, rotulo in self.CAMPOS]
        for ev in (dados.get("eventos") or [])[:20]:
            linhas.append(
                f"Evento {_quando(ev.get('em'))}: {ev.get('tipo')} "
                f"{ev.get('codigo_erro') or ''}"
            )
        texto = "\n".join(linhas)
        # Defesa extra: nunca copiar algo que pareça segredo.
        for marcador in ("Bearer ", "sk_", "client_secret"):
            if marcador in texto.lower():
                texto = texto.replace(marcador, "***")
        QApplication.clipboard().setText(texto)
        QMessageBox.information(
            self, "Diagnóstico", "Diagnóstico copiado (sem segredos)."
        )


# -------------------------------------------------------------------- backup


class PaginaBackup(_PaginaSimples):
    TITULO = "Backup"
    SUBTITULO = (
        "O backup local funciona em qualquer estado da licença. O espelho no "
        "Neon só é habilitado após aceite do termo (LGPD)."
    )

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        self._horario = CampoTexto("Horário (HH:MM)", valor="02:00", maximo=5)
        self._retencao = CampoTexto("Retenção (dias)", valor="14", maximo=3)
        self._destino = CampoTexto("Diretório local", maximo=500)
        self._espelho = CampoCheck("Enviar espelho ao Neon")
        self._espelho.habilitar(False)  # só o termo habilita
        self._corpo.addWidget(em_volta(self._horario))
        self._corpo.addWidget(em_volta(self._retencao))
        self._corpo.addWidget(em_volta(self._destino))
        self._corpo.addWidget(self._espelho.widget)

        self._lbl_estado = QLabel("")
        self._lbl_estado.setWordWrap(True)
        self._lbl_estado.setAlignment(Qt.AlignmentFlag.AlignTop)
        estado_muted(self._lbl_estado)
        self._corpo.addWidget(self._lbl_estado)

        linha1 = QHBoxLayout()
        self._btn_salvar = QPushButton("Salvar configuração")
        estado_primario(self._btn_salvar)
        self._btn_salvar.clicked.connect(self._salvar)
        self._btn_executar = QPushButton("Backup manual agora")
        estado_secundario(self._btn_executar)
        self._btn_executar.clicked.connect(self._executar)
        linha1.addStretch(1)
        linha1.addWidget(self._btn_salvar)
        linha1.addWidget(self._btn_executar)
        self._corpo.addLayout(linha1)

        linha2 = QHBoxLayout()
        self._btn_termo = QPushButton("Aceitar termo de backup em nuvem")
        estado_secundario(self._btn_termo)
        self._btn_termo.clicked.connect(self._aceitar_termo)
        self._btn_revogar = QPushButton("Desativar nuvem")
        estado_secundario(self._btn_revogar)
        self._btn_revogar.clicked.connect(self._revogar_termo)
        linha2.addStretch(1)
        linha2.addWidget(self._btn_termo)
        linha2.addWidget(self._btn_revogar)
        self._corpo.addLayout(linha2)
        self._carregar()

    def _carregar(self) -> None:
        def ok_config(resp: dict) -> None:
            dados = resp.get("data", resp) if isinstance(resp, dict) else {}
            self._horario.definir(dados.get("horario") or "02:00")
            self._retencao.definir(dados.get("retencao_dias") or 14)
            self._destino.definir(dados.get("destino"))
            self._espelho.definir(bool(dados.get("neon_espelho")))
            self._lbl_estado.setText(
                f"Último backup local: {_quando(dados.get('ultimo_backup_em'))} · "
                f"Último envio Neon: {_quando(dados.get('ultimo_envio_neon_em'))}"
            )

        def ok_termo(resp: dict) -> None:
            dados = resp.get("data", resp) if isinstance(resp, dict) else {}
            aceito = bool(dados.get("aceito"))
            self._espelho.definir(aceito)
            self._btn_termo.setEnabled(not aceito)
            self._btn_revogar.setEnabled(aceito)

        tarefas.rodar(self._api.config_backup, ok_config, self._erro)
        tarefas.rodar(self._api.termo_backup, ok_termo, self._erro)

    def _salvar(self) -> None:
        if self._modo_leitura:
            return

        def ok(_) -> None:
            QMessageBox.information(self, "Backup", "Configuração salva.")
            self._carregar()

        payload = {
            "horario": self._horario.valor(),
            "retencao_dias": self._retencao.valor(),
            "destino": self._destino.valor() or None,
        }
        tarefas.rodar(
            lambda: self._api.salvar_config_backup(payload), ok, self._erro
        )

    def _executar(self) -> None:
        def ok(resp: dict) -> None:
            dados = resp.get("data", resp) if isinstance(resp, dict) else {}
            if dados.get("ok"):
                estado_sucesso(self._lbl_estado)
                self._lbl_estado.setText(
                    f"Backup concluído: {dados.get('caminho')} "
                    f"({dados.get('tamanho')} bytes)."
                )
            else:
                estado_atencao(self._lbl_estado)
                self._lbl_estado.setText(str(dados.get("mensagem")))

        tarefas.rodar(self._api.executar_backup, ok, self._erro)

    def _aceitar_termo(self) -> None:
        if self._modo_leitura:
            return
        resp = QMessageBox.question(
            self,
            "Termo de backup em nuvem",
            "Você autoriza o envio de cópias do banco (incluindo dados pessoais "
            "e fiscais) ao Neon? Essa decisão fica auditada.",
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        tarefas.rodar(
            lambda: self._api.registrar_termo_backup(True),
            lambda _: self._carregar(),
            self._erro,
        )

    def _revogar_termo(self) -> None:
        tarefas.rodar(
            lambda: self._api.registrar_termo_backup(False),
            lambda _: self._carregar(),
            self._erro,
        )


class PaginaConsolidacao(_PaginaSimples):
    TITULO = "Consolidação"
    SUBTITULO = (
        "Cadastros mestres descem da matriz, relatórios são lidos do Neon e "
        "duplicatas de clientes vão para a fila de conflitos."
    )

    def __init__(self, api: Api, modo_leitura: bool = False) -> None:
        super().__init__(api, modo_leitura)
        linha = QHBoxLayout()
        self._btn_descer = QPushButton("Descer mestres")
        estado_secundario(self._btn_descer)
        self._btn_descer.clicked.connect(self._descer)
        self._btn_relatorio = QPushButton("Atualizar relatório")
        estado_secundario(self._btn_relatorio)
        self._btn_relatorio.clicked.connect(self._carregar_relatorio)
        self._btn_conflitos = QPushButton("Atualizar conflitos")
        estado_secundario(self._btn_conflitos)
        self._btn_conflitos.clicked.connect(self._carregar_conflitos)
        linha.addStretch(1)
        linha.addWidget(self._btn_descer)
        linha.addWidget(self._btn_relatorio)
        linha.addWidget(self._btn_conflitos)
        self._corpo.addLayout(linha)

        self._lbl_mestres = QLabel("Mestres: —")
        self._lbl_mestres.setAlignment(Qt.AlignmentFlag.AlignTop)
        estado_muted(self._lbl_mestres)
        self._corpo.addWidget(self._lbl_mestres)

        self._lbl_relatorio = QLabel("Relatório: —")
        self._lbl_relatorio.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._lbl_relatorio.setWordWrap(True)
        estado_muted(self._lbl_relatorio)
        self._corpo.addWidget(self._lbl_relatorio)

        self._lbl_conflitos = QLabel("Conflitos: —")
        self._lbl_conflitos.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._lbl_conflitos.setWordWrap(True)
        estado_muted(self._lbl_conflitos)
        self._corpo.addWidget(self._lbl_conflitos, 1)
        self._carregar_relatorio()
        self._carregar_conflitos()

    def _descer(self) -> None:
        if self._modo_leitura:
            return

        def ok(saida: dict) -> None:
            dados = saida.get("data", saida) if isinstance(saida, dict) else {}
            aplicados = dados.get("aplicados") or {}
            self._lbl_mestres.setText(
                "Mestres aplicados: "
                + (", ".join(f"{k}: {v}" for k, v in aplicados.items()) or "nenhum")
            )
            estado_sucesso(self._lbl_mestres)

        tarefas.rodar(self._api.descer_mestres, ok, self._erro)

    def _carregar_relatorio(self) -> None:
        def ok(saida: dict) -> None:
            dados = saida.get("data", saida) if isinstance(saida, dict) else {}
            linhas = [f"Atualizado em: {_quando(dados.get('ultima_atualizacao'))}"]
            for item in dados.get("por_filial") or []:
                linhas.append(
                    f"Filial {item.get('filial_id')}: {item.get('quantidade')} vendas · "
                    f"R$ {item.get('total')}"
                )
            linhas.append(f"Total geral: R$ {dados.get('total_geral', '0')}")
            linhas.append(str(dados.get("observacao") or ""))
            self._lbl_relatorio.setText("<br>".join(linhas))

        tarefas.rodar(self._api.relatorio_consolidado, ok, self._erro)

    def _carregar_conflitos(self) -> None:
        def ok(saida: dict) -> None:
            dados = saida.get("data", saida) if isinstance(saida, dict) else {}
            itens = dados.get("itens") or []
            if not itens:
                self._lbl_conflitos.setText("Nenhum conflito de cliente.")
            else:
                self._lbl_conflitos.setText(
                    "<br>".join(
                        f"• {i.get('documento')} — filiais {i.get('filiais')}"
                        for i in itens
                    )
                )

        tarefas.rodar(self._api.conflitos_clientes, ok, self._erro)
