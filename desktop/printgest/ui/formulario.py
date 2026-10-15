"""Campos de formulário de cadastro (mockups 2.x) + grade de duas colunas.

Cada campo conhece seu rótulo em minúsculas-título (padrão do design system),
expõe `valor()`/`definir()` e pode ser marcado obrigatório com * (validação
simples usada antes do POST).
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from printgest.ui.widgets import aplicar_estilo

MASCARA_CPF = "000.000.000-00;_"
MASCARA_CNPJ = "00.000.000/0000-00;_"
MASCARA_CEP = "00000-000;_"
MASCARA_UF = "AA"


class CampoForm:
    """Base — subclasses definem o widget e a conversão de valor."""

    # Campos que ocupam a largura toda do formulário (ex.: grade de itens).
    largo = False

    def __init__(self, rotulo: str | None = None) -> None:
        self._rotulo: QLabel | None = None
        self._obrigatorio = False
        if rotulo:
            self._rotulo = QLabel(rotulo.upper())
            self._rotulo.setObjectName("labelForm")

    @property
    def rotulo_widget(self) -> QWidget | None:
        return self._rotulo

    @property
    def widget(self) -> QWidget:
        raise NotImplementedError

    def valor(self) -> object:
        raise NotImplementedError

    def definir(self, valor: object) -> None:
        raise NotImplementedError

    def habilitar(self, ligado: bool) -> None:
        self.widget.setEnabled(ligado)

    def larga(self) -> "CampoForm":
        """Marca o campo para ocupar a linha inteira (2 colunas) da grade."""
        self.largo = True
        return self

    def visivel(self, ligado: bool) -> None:
        """Mostra/oculta o campo inteiro (rótulo acima + controle)."""
        alvo = getattr(self, "_celula", None) or self.widget
        alvo.setVisible(ligado)

    def obrigatorio(self, ligado: bool = True) -> "CampoForm":
        self._obrigatorio = ligado
        if self._rotulo is not None and ligado:
            self._rotulo.setText(f"{self._rotulo.text()} *")
        return self

    def valido(self) -> bool:
        if not self._obrigatorio:
            return True
        valor = self.valor()
        return isinstance(valor, str) and valor.strip() != "" or valor is not None and valor != ""


class CampoTexto(CampoForm):
    def __init__(self, rotulo: str, valor="", mono: bool = False, maximo=200, mascara="") -> None:
        super().__init__(rotulo)
        self._edicao = QLineEdit(valor)
        self._edicao.setMaxLength(maximo)
        if mascara:
            self._edicao.setInputMask(mascara)
        if mono:
            self._edicao.setProperty("mono", "true")
            aplicar_estilo(self._edicao)

    @property
    def widget(self) -> QLineEdit:
        return self._edicao

    def valor(self) -> str:
        texto = self._edicao.text().strip()
        if self._edicao.inputMask() and self._mask_vazia():
            return ""
        return texto.replace("_", "") if self._edicao.inputMask() else texto

    def _mask_vazia(self) -> bool:
        """True quando não há dado digitado — só restaram os separadores da máscara."""
        base = self._edicao.inputMask().split(";")[0]
        if not base:
            return not self._edicao.text().strip()
        esqueleto = []
        entre_barras = False
        for ch in base:
            if entre_barras:
                esqueleto.append(ch)
                entre_barras = False
            elif ch == "\\":
                entre_barras = True
            elif ch not in "AaNnXx90Dd#":
                esqueleto.append(ch)
        return self._edicao.text() == "".join(esqueleto)

    def definir(self, valor) -> None:
        self._edicao.setText("" if valor is None else str(valor))

    def definir_mascara(self, mascara: str) -> None:
        self._edicao.setInputMask(mascara)


class CampoArea(CampoForm):
    def __init__(self, rotulo: str, valor="", linhas: int = 3) -> None:
        super().__init__(rotulo)
        self._area = QPlainTextEdit(valor)
        self._area.setMinimumHeight(20 + linhas * 16)
        self._area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

    @property
    def widget(self) -> QPlainTextEdit:
        return self._area

    def valor(self) -> str:
        return self._area.toPlainText().strip()

    def definir(self, valor) -> None:
        self._area.setPlainText("" if valor is None else str(valor))


class CampoData(CampoForm):
    def __init__(self, rotulo: str, aceita_sem_data: bool = True) -> None:
        super().__init__(rotulo)
        self._sem = QCheckBox("Sem data")
        self._data = QDateEdit()
        self._data.setCalendarPopup(True)
        self._data.setDisplayFormat("dd/MM/yyyy")
        self._data.setMinimumDate(QDate(1900, 1, 1))
        self._data.setMaximumDate(QDate(2100, 12, 31))
        # No mínimo da faixa o QDateEdit exibe `specialValueText` — usamos um
        # espaço para o campo "sem data" ficar realmente vazio (nunca 01/01/1900).
        self._data.setSpecialValueText(" ")
        self._aceita_sem_data = aceita_sem_data
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)
        linha.addWidget(self._data, 1)
        if aceita_sem_data:
            linha.addWidget(self._sem)
            self._sem.toggled.connect(self._sem_data_mudou)
        self._caixa = caixa
        # Padrão dos cadastros: data opcional e vazia (sem data gravada).
        self._sem.setChecked(aceita_sem_data)
        self._sem_data_mudou(aceita_sem_data)

    @property
    def widget(self) -> QWidget:
        return self._caixa

    def _sem_data_mudou(self, ligado: bool) -> None:
        self._data.setDisabled(ligado)
        if ligado:
            self._data.setDate(self._data.minimumDate())
        elif self._data.date() == self._data.minimumDate():
            self._data.setDate(QDate.currentDate())

    def valor(self) -> date | None:
        if self._aceita_sem_data and self._sem.isChecked():
            return None
        d = self._data.date()
        return date(d.year(), d.month(), d.day())

    def definir(self, valor) -> None:
        if valor is None or valor == "":
            if self._aceita_sem_data:
                self._sem.setChecked(True)
            else:
                self._data.setDate(QDate.currentDate())
            return
        d = QDate.fromString(str(valor)[:10], "yyyy-MM-dd")
        if d.isValid():
            self._data.setDate(d)
            if self._aceita_sem_data:
                self._sem.setChecked(False)

    def habilitar(self, ligado: bool) -> None:
        self._caixa.setEnabled(ligado)


class CampoDataHora(CampoForm):
    """Data + hora em dois controles lado a lado (início/fim de um agendamento)."""

    def __init__(self, rotulo: str, obrigatorio: bool = True) -> None:
        super().__init__(rotulo)
        self._obrigatorio_fixo = obrigatorio
        self._data = QDateEdit()
        self._data.setCalendarPopup(True)
        self._data.setDisplayFormat("dd/MM/yyyy")
        self._data.setDate(QDate.currentDate())
        self._hora = QTimeEdit()
        self._hora.setDisplayFormat("HH:mm")
        self._hora.setTime(QTime(9, 0))
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(8)
        linha.addWidget(self._data, 1)
        linha.addWidget(self._hora, 1)
        self._caixa = caixa

    @property
    def widget(self) -> QWidget:
        return self._caixa

    def valor(self) -> datetime | None:
        d = self._data.date()
        if not d.isValid():
            return None
        t = self._hora.time()
        return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())

    def definir(self, valor) -> None:
        if valor is None or valor == "":
            self._data.setDate(QDate.currentDate())
            self._hora.setTime(QTime(9, 0))
            return
        if isinstance(valor, datetime):
            dt = valor
        else:
            dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
        self._data.setDate(QDate(dt.year, dt.month, dt.day))
        self._hora.setTime(QTime(dt.hour, dt.minute))

    def habilitar(self, ligado: bool) -> None:
        self._caixa.setEnabled(ligado)


class CampoCombo(CampoForm):
    def __init__(self, rotulo: str, opcoes: list[tuple[str, str]], padrao: str | None = None) -> None:
        super().__init__(rotulo)
        self._combo = QComboBox()
        for valor, rotulo_op in opcoes:
            self._combo.addItem(rotulo_op, valor)
        if padrao is not None:
            indice = self._combo.findData(padrao)
            if indice >= 0:
                self._combo.setCurrentIndex(indice)

    @property
    def widget(self) -> QComboBox:
        return self._combo

    def valor(self) -> str:
        return self._combo.currentData()

    def definir(self, valor) -> None:
        indice = self._combo.findData(valor)
        self._combo.setCurrentIndex(indice)  # -1 = sem seleção (valor None)

    def alterar_opcoes(self, opcoes: list[tuple[str, str]], padrao: str | None = None) -> None:
        self._combo.blockSignals(True)
        atual = self.valor()
        self._combo.clear()
        for valor, rotulo_op in opcoes:
            self._combo.addItem(rotulo_op, valor)
        alvo = padrao or atual
        indice = self._combo.findData(alvo)
        if indice >= 0:
            self._combo.setCurrentIndex(indice)
        self._combo.blockSignals(False)


class CampoCheck(CampoForm):
    def __init__(self, rotulo: str) -> None:
        # O próprio checkbox já exibe o rótulo; sem QLabel de campo (evita texto 2×).
        super().__init__(None)
        self._check = QCheckBox(rotulo)

    @property
    def widget(self) -> QCheckBox:
        return self._check

    def valor(self) -> bool:
        return self._check.isChecked()

    def definir(self, valor) -> None:
        self._check.setChecked(bool(valor))


class CampoArquivo(CampoForm):
    """Caminho de arquivo (ex.: foto) com botão para escolher no disco."""

    def __init__(
        self, rotulo: str, filtro: str = "Imagens (*.png *.jpg *.jpeg *.webp)"
    ) -> None:
        super().__init__(rotulo)
        self._filtro = filtro
        self._edicao = QLineEdit()
        self._edicao.setReadOnly(True)
        self._edicao.setPlaceholderText("Nenhum arquivo selecionado")
        botao = QPushButton("Escolher…")
        botao.setObjectName("acaoLinha")
        botao.clicked.connect(self._escolher)
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        linha.addWidget(self._edicao, 1)
        linha.addWidget(botao)
        self._caixa = caixa

    @property
    def widget(self) -> QWidget:
        return self._caixa

    def _escolher(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self._caixa, "Selecionar arquivo", "", self._filtro
        )
        if caminho:
            self._edicao.setText(caminho)

    def valor(self) -> str:
        return self._edicao.text().strip()

    def definir(self, valor) -> None:
        self._edicao.setText("" if valor is None else str(valor))

    def habilitar(self, ligado: bool) -> None:
        self._caixa.setEnabled(ligado)


def grade_campos() -> QGridLayout:
    """Grade de 2 colunas iguais; cada célula recebe rótulo acima do controle."""
    grade = QGridLayout()
    grade.setHorizontalSpacing(16)
    grade.setVerticalSpacing(10)
    grade.setColumnStretch(0, 1)
    grade.setColumnStretch(1, 1)
    return grade


def em_volta(campo: CampoForm) -> QWidget:
    """Empilha rótulo acima do controle (padrão do formulário, evita G1)."""
    caixa = QWidget()
    coluna = QVBoxLayout(caixa)
    coluna.setContentsMargins(0, 0, 0, 0)
    coluna.setSpacing(4)
    if campo.rotulo_widget is not None:
        coluna.addWidget(campo.rotulo_widget)
    coluna.addWidget(campo.widget)
    campo._celula = caixa
    return caixa


def dispor_campos(grade: QGridLayout, campos: list) -> None:
    """Dispõe os campos em 2 colunas; campos marcados com `larga()` ocupam a linha."""
    linha = 0
    pendente: list = []
    for campo in campos:
        if getattr(campo, "largo", False):
            if pendente:
                grade.addWidget(em_volta(pendente.pop()), linha, 0)
                linha += 1
            grade.addWidget(em_volta(campo), linha, 0, 1, 2)
            linha += 1
            continue
        pendente.append(campo)
        if len(pendente) == 2:
            grade.addWidget(em_volta(pendente[0]), linha, 0)
            grade.addWidget(em_volta(pendente[1]), linha, 1)
            pendente = []
            linha += 1
    if pendente:
        grade.addWidget(em_volta(pendente[0]), linha, 0)


def formatar_moeda(valor) -> str:
    """'84.70' → 'R$ 84,70'; None/vazio → ''."""
    if valor is None or valor == "":
        return ""
    from decimal import Decimal, InvalidOperation

    texto = str(valor).strip()
    if not texto:
        return ""
    try:
        dec = Decimal(texto)
    except (InvalidOperation, ValueError):
        return texto
    inteiro, _, decimais = f"{abs(dec):.2f}".partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    sinal = "-" if dec < 0 else ""
    return f"{sinal}R$ {inteiro},{decimais}"


def formatar_percentual(valor) -> str:
    """'50.00' → '50'; '33.50' → '33,5'; None/vazio → ''."""
    if valor is None or valor == "":
        return ""
    from decimal import Decimal, InvalidOperation

    try:
        dec = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return str(valor)
    texto = f"{dec:.2f}".rstrip("0").rstrip(".")
    return (texto or "0").replace(".", ",")


class CampoValor(CampoForm):
    """Valor numerário: prefixo (padrão 'R$') + linha de texto livre, Decimal em `valor()`.

    Aceita "1.234,56", "1234,56", "84,70", "38" — retorna Decimal; vazio vira None.
    """

    def __init__(self, rotulo: str, valor="", prefixo: str = "R$") -> None:
        super().__init__(rotulo)
        self._prefixo = prefixo
        self._edicao = QLineEdit(valor)
        self._edicao.setMinimumWidth(80)
        caixa = QWidget()
        linha = QHBoxLayout(caixa)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(6)
        if prefixo:
            rot = QLabel(prefixo)
            rot.setObjectName("labelForm")
            rot.setMinimumWidth(28)
            rot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            linha.addWidget(rot)
        linha.addWidget(self._edicao, 1)
        self._caixa = caixa

    @property
    def widget(self) -> QWidget:
        return self._caixa

    def _para_decimal(self, texto: str):
        return para_decimal(texto, self._prefixo)

    def valor(self):
        from decimal import Decimal

        dec = self._para_decimal(self._edicao.text())
        return None if dec is None else Decimal(dec)

    def definir(self, valor) -> None:
        if valor is None or valor == "":
            self._edicao.clear()
            return
        t = str(valor).strip()
        if "," in t or "." not in t:
            self._edicao.setText(t)
            return
        inteiros, _, dec = t.partition(".")
        self._edicao.setText(f"{inteiros},{dec[:2]}" if dec else inteiros)

    @property
    def edicao(self) -> QLineEdit:
        return self._edicao


def adicionar_linha(grade: QGridLayout, linha: int, *campos: CampoForm):
    """Posiciona até 2 campos por linha (rótulo acima de cada controle)."""
    for coluna, campo in enumerate(campos[:2]):
        grade.addWidget(em_volta(campo), linha, coluna)


def adicionar_linha_larga(grade: QGridLayout, linha: int, campo: CampoForm):
    """Campo que ocupa as 2 colunas do formulário (ex.: grade de itens)."""
    grade.addWidget(em_volta(campo), linha, 0, 1, 2)


def data_iso(valor):
    """`date` → 'AAAA-MM-DD' (JSON-safe); None vira None."""
    if valor is None or valor == "":
        return None
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    texto = str(valor)[:10]
    return texto if texto else None


def limpo(valor):
    """Campo em branco/whitespace vira None; demais valores passam intactos.

    Usado nos `_payload` dos cadastros — o backend prefere `null` a string vazia.
    """
    if isinstance(valor, str) and valor.strip() == "":
        return None
    return valor


def numero(campo, padrao="0") -> str:
    """Valor de campo numérico como string; `None` vira `padrao`."""
    valor = campo.valor()
    return str(valor) if valor is not None else padrao


def primeiro_valor(dado: dict, *chaves: str) -> str:
    """Primeiro valor não vazio entre `chaves` (ex.: celular → telefone → e-mail)."""
    for chave in chaves:
        valor = dado.get(chave)
        if valor:
            return str(valor)
    return ""


def para_decimal(texto, prefixo="R$"):
    """Texto monetário ('1.234,56', '84,70', '38') → `Decimal`; vazio/inválido → `None`.

    Trata o padrão brasileiro: milhar com ponto e decimal com vírgula — usada
    pelos campos de valor e pela grade de itens (evita '1.500,00' virar 0).
    """
    from decimal import Decimal, InvalidOperation

    texto = str(texto).replace("\u00a0", " ").replace(prefixo, "").strip()
    if not texto:
        return None
    compacto = texto.replace(" ", "")
    if not compacto:
        return None
    if "," in compacto and "." in compacto:
        compacto = compacto.replace(".", "")
    compacto = compacto.replace(",", ".")
    try:
        return Decimal(compacto)
    except (InvalidOperation, ValueError):
        return None


def formatar_data_iso(valor) -> str:
    """'2026-09-25' (ou ISO truncado) → '25/09/2026'; vazio/inválido → ''."""
    if not valor:
        return ""
    partes = str(valor)[:10].split("-")
    if len(partes) != 3:
        return ""
    ano, mes, dia = partes
    return f"{dia}/{mes}/{ano}"


def formatar_data_hora(valor) -> str:
    """ISO 'AAAA-MM-DDTHH:MM:SS' (ou só data) → 'DD/MM/AAAA HH:MM'; vazio → ''."""
    if not valor:
        return ""
    texto = str(valor)[:19].replace("T", " ")
    partes = texto.split(" ")
    data = formatar_data_iso(partes[0])
    if not data:
        return ""
    return f"{data} {partes[1][:5]}" if len(partes) == 2 else data


def rotulo_secao(texto: str) -> QLabel:
    lbl = QLabel(texto.upper())
    lbl.setObjectName("secaoForm")
    return lbl