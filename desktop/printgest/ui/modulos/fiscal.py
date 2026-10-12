"""Módulo Fiscal (PRD v2.1 §1.6 / telas_e_fluxos §1.6).

Duas telas sob o menu "Fiscal", reunidas num host com sub-abas:

- **Documentos Fiscais** — consulta dos documentos emitidos (status, chave,
  XML/DANFE, vinculação com venda/O.S.). Somente leitura.
- **Contingência** — aviso de gateway indisponível + pendências (rascunhos,
  em processamento, rejeitados e documentos marcados em contingência).

A **emissão** de NF-e/NFC-e depende de um gateway fiscal externo que não faz
parte deste produto: por isso o módulo é somente leitura e a tela de
contingência é explícita sobre a indisponibilidade (nada é simulado).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import printgest.core.tarefas as tarefas
from printgest.ui.formulario import (
    CampoArea,
    CampoCheck,
    CampoTexto,
    CampoValor,
    formatar_data_hora,
    formatar_moeda,
)
from printgest.ui.modulos.pagina_crud import PaginaCrud
from printgest.ui.tabela import TabelaDensa
from printgest.ui.widgets import ElideLabel, badge, botao_com_atalho

_STATUS_FISCAL = {
    "rascunho": "RASCUNHO",
    "processando": "PROCESSANDO",
    "autorizado": "AUTORIZADO",
    "rejeitado": "REJEITADO",
    "cancelado": "CANCELADO",
}
_MODELO = {"nfe": "NF-e", "nfce": "NFC-e"}
_PENDENTES = ("rascunho", "processando", "rejeitado")


def _status_rotulo(valor) -> str:
    return _STATUS_FISCAL.get(valor, str(valor or "").upper())


def _modelo_rotulo(valor) -> str:
    return _MODELO.get(valor, str(valor or "").upper())


def _documento_pendente(doc: dict) -> bool:
    return doc.get("contingencia") or doc.get("status") in _PENDENTES


# ======================================================= documentos fiscais


class PaginaDocumentosFiscais(PaginaCrud):
    """Consulta de documentos fiscais emitidos — somente leitura."""

    ENTIDADE = "fiscal/documentos"
    ROTULO_PAGINA = "Documentos Fiscais"
    ROTULO_NOVO = "Documento Fiscal"
    GRUPO_LISTA = "DOCUMENTOS EMITIDOS"
    LUGAR_BUSCA = "Buscar por número, chave de acesso ou cliente..."
    CAMPO_NOME = "chave_acesso"
    VAZIO = "Nenhum documento fiscal encontrado para os filtros atuais."
    CHAVE_FILTRO = "status_fiscal"
    FILTROS = [
        ("", "Todos"),
        ("rascunho", "Rascunhos"),
        ("processando", "Processando"),
        ("autorizado", "Autorizados"),
        ("rejeitado", "Rejeitados"),
        ("cancelado", "Cancelados"),
    ]
    CHAVES = [
        "id",
        "modelo",
        "numero",
        "serie",
        "status",
        "valor_nota",
        "chave_acesso",
        "contingencia",
        "created_at",
    ]
    COLUNAS = [
        "Nº",
        "Modelo",
        "Número",
        "Série",
        "Status",
        "Valor",
        "Chave de Acesso",
        "Contingência",
        "Emitido em",
    ]
    PESOS = [1, 2, 2, 1, 3, 2, 6, 2, 3]

    def _secoes(self):
        self._f_modelo = CampoTexto("Modelo")
        self._f_numero = CampoTexto("Número")
        self._f_serie = CampoTexto("Série")
        self._f_status = CampoTexto("Status")
        self._f_valor = CampoValor("Valor da Nota")
        self._f_chave = CampoTexto("Chave de Acesso")
        self._f_protocolo = CampoTexto("Protocolo")
        self._f_contingencia = CampoCheck("Emitido em contingência")
        self._f_cliente = CampoTexto("Cliente")
        self._f_emitido = CampoTexto("Emitido em")
        self._f_vinculo = CampoTexto("Vinculado a")
        self._f_mensagem = CampoArea("Mensagem de retorno", linhas=3)
        self._f_arquivos = CampoTexto("Arquivos (XML / DANFE)")
        return [
            (
                "Documento",
                [self._f_modelo, self._f_numero, self._f_serie, self._f_status],
            ),
            (
                "Autorização",
                [self._f_valor, self._f_chave, self._f_protocolo, self._f_emitido],
            ),
            (
                "Rastreabilidade",
                [self._f_cliente, self._f_vinculo, self._f_contingencia, self._f_arquivos],
            ),
            ("Retorno", [self._f_mensagem]),
        ]

    def _preencher_campos(self, dado: dict) -> None:
        self._f_modelo.definir(_modelo_rotulo(dado.get("modelo")))
        self._f_numero.definir(dado.get("numero"))
        self._f_serie.definir(dado.get("serie"))
        self._f_status.definir(_status_rotulo(dado.get("status")))
        self._f_valor.definir(dado.get("valor_nota"))
        self._f_chave.definir(dado.get("chave_acesso") or "—")
        self._f_protocolo.definir(dado.get("protocolo") or "—")
        self._f_contingencia.definir(bool(dado.get("contingencia")))
        self._f_cliente.definir(dado.get("cliente_nome") or "—")
        self._f_emitido.definir(formatar_data_hora(dado.get("created_at")) or "—")
        self._f_vinculo.definir(self._vinculo(dado))
        self._f_mensagem.definir(dado.get("mensagem_retorno"))
        self._f_arquivos.definir(self._arquivos(dado))

    @staticmethod
    def _vinculo(dado: dict) -> str:
        if dado.get("venda_balcao_id"):
            return f"Venda balcão #{dado['venda_balcao_id']}"
        if dado.get("ordem_servico_id"):
            return f"O.S. #{dado['ordem_servico_id']}"
        return "—"

    @staticmethod
    def _arquivos(dado: dict) -> str:
        partes = []
        if dado.get("xml_path"):
            partes.append("XML")
        if dado.get("danfe_path"):
            partes.append("DANFE")
        return " / ".join(partes) if partes else "—"

    def _formatar_texto(self, dado: dict, chave: str) -> str:
        if chave == "modelo":
            return _modelo_rotulo(dado.get(chave))
        if chave == "status":
            return _status_rotulo(dado.get(chave))
        if chave == "valor_nota":
            return formatar_moeda(dado.get(chave))
        if chave == "contingencia":
            return "Sim" if dado.get(chave) else "Não"
        if chave == "created_at":
            return formatar_data_hora(dado.get(chave))
        return super()._formatar_texto(dado, chave)

    # -------------------------------------------------------------- leitura

    def _instalar_atalhos(self) -> None:
        # Consulta: sem cadastro (nenhum F6/F10).
        return

    def _aplicar_modo_leitura_acoes(self) -> None:
        super()._aplicar_modo_leitura_acoes()
        for campo in self._campos():
            campo.habilitar(False)
        for botao in (self._btn_novo, self._btn_salvar, self._btn_cancelar):
            botao.hide()


# ============================================================= contingência


class PaginaContingencia(QWidget):
    """Aviso de gateway indisponível + pendências fiscais."""

    def __init__(self, api, modo_leitura: bool = False) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._seq = 0

        col = QVBoxLayout(self)
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(10)
        col.addWidget(self._barra())
        col.addWidget(self._aviso())
        col.addWidget(self._tabela_card(), 1)
        self.recarregar()

    def _barra(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(12)
        titulo = ElideLabel("Contingência Fiscal")
        titulo.setObjectName("titulo")
        linha.addWidget(titulo, 1)
        self._badge_gateway = badge("GATEWAY INDISPONÍVEL", "atencao")
        self._badge_pendentes = badge("Pendências: –", "primary")
        atualizar, _btn = botao_com_atalho("Atualizar", "")
        _btn.clicked.connect(self.recarregar)
        linha.addWidget(self._badge_gateway)
        linha.addWidget(self._badge_pendentes)
        linha.addWidget(atualizar)
        return caixa

    def _aviso(self) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("card")
        col = QVBoxLayout(caixa)
        col.setContentsMargins(16, 14, 16, 14)
        col.setSpacing(8)
        self._titulo_aviso = ElideLabel("Situação do gateway fiscal")
        self._titulo_aviso.setObjectName("titulo")
        col.addWidget(self._titulo_aviso)
        self._mensagem = QLabel("")
        self._mensagem.setObjectName("subtitulo")
        self._mensagem.setWordWrap(True)
        col.addWidget(self._mensagem)
        self._contagens = QLabel("")
        self._contagens.setObjectName("subtitulo")
        self._contagens.setWordWrap(True)
        col.addWidget(self._contagens)
        return caixa

    def _tabela_card(self) -> QWidget:
        caixa = QWidget()
        caixa.setObjectName("card")
        col = QVBoxLayout(caixa)
        col.setContentsMargins(0, 8, 0, 0)
        col.setSpacing(0)
        self._tabela = TabelaDensa(
            ["id", "modelo", "numero", "status", "contingencia", "valor_nota", "created_at"],
            ["Nº", "Modelo", "Número", "Status", "Contingência", "Valor", "Emitido em"],
            [1, 2, 2, 3, 2, 2, 3],
        )
        self._tabela.formata = self._formatar
        self._tabela.estado_vazio(
            "Nenhuma pendência fiscal. Assim que o gateway for integrado, os "
            "documentos aparecerão aqui para reenvio."
        )
        col.addWidget(self._tabela, 1)
        return caixa

    def _formatar(self, dado: dict, chave: str) -> str:
        if chave == "id":
            ident = dado.get("id")
            return f"#{ident:05d}" if isinstance(ident, int) else ""
        if chave == "modelo":
            return _modelo_rotulo(dado.get(chave))
        if chave == "status":
            return _status_rotulo(dado.get(chave))
        if chave == "contingencia":
            return "Sim" if dado.get(chave) else "Não"
        if chave == "valor_nota":
            return formatar_moeda(dado.get(chave))
        if chave == "created_at":
            return formatar_data_hora(dado.get(chave))
        valor = dado.get(chave, "")
        return "" if valor is None else str(valor)

    def recarregar(self) -> None:
        self._seq += 1
        seq = self._seq

        def _com_resumo(resumo: dict | None) -> None:
            if seq != self._seq:
                return
            self._aplicar_resumo(resumo or {})
            tarefas.rodar(
                lambda: self._api.documentos_fiscais(limit=200),
                on_ok=lambda saida: self._com_lista(saida, seq),
                on_erro=lambda msg: self._erro(msg, seq),
            )

        tarefas.rodar(
            lambda: self._api.resumo_fiscal(),
            on_ok=_com_resumo,
            on_erro=lambda msg: self._erro(msg, seq),
        )

    def _aplicar_resumo(self, resumo: dict) -> None:
        pendentes = resumo.get("pendentes", 0)
        self._badge_pendentes.setText(f"Pendências: {pendentes}")
        self._mensagem.setText(
            resumo.get("mensagem")
            or "Situação do gateway fiscal indisponível no momento."
        )
        self._contagens.setText(
            "Documentos: {total} · Autorizados: {aut} · Rejeitados: {rej} · "
            "Em contingência: {cont}".format(
                total=resumo.get("total", 0),
                aut=resumo.get("por_status", {}).get("autorizado", 0),
                rej=resumo.get("por_status", {}).get("rejeitado", 0),
                cont=resumo.get("em_contingencia", 0),
            )
        )
        disponivel = bool(resumo.get("gateway_disponivel"))
        self._badge_gateway.setText(
            "GATEWAY DISPONÍVEL" if disponivel else "GATEWAY INDISPONÍVEL"
        )
        self._badge_gateway.setProperty(
            "badgeStyle", "primary" if disponivel else "atencao"
        )
        self._badge_gateway.style().unpolish(self._badge_gateway)
        self._badge_gateway.style().polish(self._badge_gateway)

    def _com_lista(self, saida: dict, seq: int) -> None:
        if seq != self._seq:
            return
        pendentes = [d for d in saida.get("data", []) if _documento_pendente(d)]
        self._tabela.preencher(pendentes)

    def _erro(self, msg: str, seq: int) -> None:
        if seq != self._seq:
            return
        self._tabela.limpar()
        QMessageBox.warning(self, "Fiscal", msg)


# ==================================================================== host


class PaginaFiscal(QWidget):
    """Menu "Fiscal": hospeda Documentos Fiscais e Contingência."""

    def __init__(self, api, modo_leitura: bool = False, nivel: str | None = None) -> None:
        super().__init__()
        self._api = api
        self._modo_leitura = modo_leitura
        self._abas = [
            ("Documentos Fiscais", PaginaDocumentosFiscais),
            ("Contingência", PaginaContingencia),
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
        self._trocar(0)

    def _barra(self) -> QWidget:
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(20, 16, 20, 0)
        linha.setSpacing(8)
        titulo = ElideLabel("Fiscal")
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
