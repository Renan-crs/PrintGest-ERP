import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
    QWidget,
)

from printgest import APP_NAME, __version__
from printgest.core import daemon
from printgest.core.api import Api, modo_estacao
from printgest.core.tarefas import rodar
from printgest.ui.ativacao import AtivacaoWindow
from printgest.ui.conexao import ConexaoWindow
from printgest.ui.login import LoginWindow
from printgest.ui.modoleitura import ModoLeituraWindow
from printgest.ui.tela_principal import TelaPrincipal
from printgest.ui.theme import aplicar_theme
from printgest.ui.widgets import icone_printgest


def _carregar_env_do_executavel(caminho: Path | None = None) -> None:
    """Instalação empacotada (estação): `.env` ao lado do exe define o servidor.

    O instalador da estação pergunta o endereço durante a instalação e grava
    `PRINTGEST_API_URL` (e `PRINTGEST_MODO_ESTACAO`) num `.env` junto ao
    `PrintGest.exe` — variável de sistema não seria lugar de configuração por
    instalação. Variáveis de ambiente reais continuam vencendo o arquivo
    (`setdefault`), útil para diagnóstico.
    """
    if caminho is None:
        if not getattr(sys, "frozen", False):
            return
        caminho = Path(sys.executable).resolve().parent / ".env"
    try:
        linhas = caminho.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for linha in linhas:
        chave, separador, valor = linha.strip().partition("=")
        chave = chave.strip()
        if separador and chave and not chave.startswith("#"):
            os.environ.setdefault(chave, valor.strip())


def _licenca_desabilitada() -> bool:
    """Dev build: login vai direto ao sistema; o licenciamento fica para a fase final."""
    return os.environ.get("PRINTGEST_LICENCA_DESABILITADA", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "sim",
    }


def _erro_inesperado(tipo: type, valor: BaseException, tb) -> None:
    """Protocolo 4: exceção não tratada não derruba a app em silêncio."""
    import traceback

    traceback.print_exception(tipo, valor, tb)
    try:
        QMessageBox.critical(
            None,
            "Erro inesperado",
            f"Ocorreu um erro inesperado.\n\n{tipo.__name__}: {valor}\n\n"
            "Os detalhes completos foram gravados no console/log.",
        )
    except Exception:
        pass  # antes do QApplication existir: só o traceback no stderr


class _Roteador:
    """Fluxo de entrada (§3.1): Licença (serial) → Login → Dashboard.

    Como em programas licenciados por serial, a ativação é pedida **na
    instalação**: na primeira execução, sem licença local, a tela de ativação
    aparece antes do login e o sistema só é liberado depois de validar o serial.
    A licença fica gravada pelo Local API Service (banco local), então nas
    execuções seguintes o login abre direto o sistema; a tela só volta a ser
    pedida se a instalação for refeita (licença ausente).

    **Modo Estação** (`estacao=True`, instalador com `PRINTGEST_API_URL`): o
    serial NÃO é pedido aqui — a licença pertence ao servidor da gráfica, que
    já responde pelo modo de leitura; a tela inicial é a de conexão.

    Com `PRINTGEST_LICENCA_DESABILITADA=true`, a etapa de licença é pulada e o
    login abre direto o sistema (desenvolvimento).
    """

    def __init__(self, api: Api, estacao: bool = False) -> None:
        self._api = api
        self._token: str | None = None
        self._janela: QWidget | None = None
        self._licenca_desabilitada = _licenca_desabilitada()
        self._estacao = estacao

    def iniciar(self) -> None:
        """Ponto de entrada: o serial precede o login (gate de instalação)."""
        if self._licenca_desabilitada or self._estacao:
            self._abrir_login()
            return
        self._verificar_licenca()

    # ------------------------------------------------------------------ ajuda

    def _fechar_janela(self) -> None:
        if self._janela is not None:
            self._janela.close()
            self._janela = None

    def _abrir(self, janela: QWidget) -> None:
        self._fechar_janela()
        self._janela = janela
        self._janela.show()

    # ---------------------------------------------------------------- licença

    def _verificar_licenca(self) -> None:
        """Consulta a situação sem sessão: o serial precede o login.

        `GET /v1/licenca` e `POST /v1/licenca/ativar` são liberados pelo
        Local API Service justamente para permitir a ativação antes de haver
        usuário autenticado.
        """
        rodar(
            lambda: self._api.situacao_licenca(),
            on_ok=self._situacao_instalacao,
            on_erro=self._sem_daemon,
        )

    def _situacao_instalacao(self, sit: dict) -> None:
        """Primeira tela da instalação: ativação se não houver licença."""
        if sit.get("status") == "nao_ativada":
            self._abrir_ativacao(sit, token=None, apos_ativacao=self._abrir_login)
        else:
            self._abrir_login()

    # ------------------------------------------------------------------- tela

    def _abrir_login(self) -> None:
        self._fechar_janela()
        janela = LoginWindow(self._api)
        janela.autenticado.connect(self._pos_login)
        janela.saida.connect(QApplication.instance().quit)
        self._janela = janela
        janela.show()

    def _pos_login(self, dados: dict) -> None:
        self._token = dados["token"]
        self._api.autenticar(dados)
        if self._licenca_desabilitada:
            self._abrir_dashboard(False)
            return
        rodar(
            lambda: self._api.situacao_licenca(self._token),
            on_ok=self._situacao,
            on_erro=self._sem_daemon,
        )

    def _sem_daemon(self, msg: str) -> None:
        caixa = QMessageBox(self._janela)
        caixa.setIcon(QMessageBox.Icon.Critical)
        caixa.setWindowTitle("Local API Service indisponível")
        caixa.setText("Não foi possível consultar o estado da licença.")
        caixa.setInformativeText(
            f"{msg}\n\nVerifique se o daemon (127.0.0.1:8000) está em execução e "
            "tente novamente."
        )
        caixa.addButton("Tentar Novamente", QMessageBox.ButtonRole.AcceptRole)
        caixa.addButton("Sair", QMessageBox.ButtonRole.RejectRole)
        if caixa.exec() == 0:
            # Antes do login não há token: repete a checagem de instalação.
            if self._token:
                rodar(
                    lambda: self._api.situacao_licenca(self._token),
                    on_ok=self._situacao,
                    on_erro=self._sem_daemon,
                )
            else:
                self._verificar_licenca()
        else:
            QApplication.instance().quit()

    def _situacao(self, sit: dict) -> None:
        status = sit["status"]
        if status == "nao_ativada":
            # Só acontece se a licença sumir entre a instalação e o login.
            self._abrir_ativacao(
                sit,
                token=self._token,
                apos_ativacao=lambda: self._abrir_dashboard(False),
            )
        elif sit["modo_leitura"]:
            self._abrir_modo_leitura(sit)
        else:
            self._abrir_dashboard(False, sit=sit)

    # ---------------------------------------------------------------- telas

    def _abrir_ativacao(
        self,
        sit: dict,
        *,
        token: str | None = None,
        apos_ativacao=None,
    ) -> None:
        contrato = ""
        if isinstance(sit, dict):
            contrato = str(sit.get("contrato") or "")
        janela = AtivacaoWindow(self._api, token=token, contrato=contrato)
        janela.ativada.connect(apos_ativacao or self._abrir_login)
        janela.saida.connect(QApplication.instance().quit)
        self._abrir(janela)

    def _abrir_modo_leitura(self, sit: dict) -> None:
        janela = ModoLeituraWindow(self._api, token=self._token, situacao=sit)
        janela.renovada.connect(lambda: self._abrir_dashboard(False))
        janela.consulta.connect(lambda: self._abrir_dashboard(True))
        janela.saida.connect(QApplication.instance().quit)
        self._abrir(janela)

    def _abrir_dashboard(self, modo_leitura: bool, sit: dict | None = None) -> None:
        if self._api.usuario is None:
            self._abrir_login()
            return
        principal = TelaPrincipal(
            self._api,
            usuario=self._api.usuario,
            modo_leitura=modo_leitura,
            base_url=self._api.base_url_display,
            situacao_licenca=sit,
        )
        principal.solicitado_logout.connect(lambda: self._abrir_login())
        self._abrir(principal)


def _preparar_daemon(app: QApplication) -> None:
    """Instalação empacotada: sobe o Local API Service antes do fluxo normal.

    A primeira execução paga o initdb do PostgreSQL embarcado (segundos); o
    diálogo indeterminado mantém o usuário informado em vez de uma janela
    congelada. Sem nada para subir (dev) a chamada é uma sondagem rápida.
    """
    if daemon.saude():
        return
    if daemon.caminho_do_backend() is None:
        return
    espera = QProgressDialog(
        "Preparando o banco de dados local...\nA primeira execução pode levar alguns segundos.",
        None,
        0,
        0,
    )
    espera.setWindowTitle(APP_NAME)
    espera.setWindowModality(Qt.WindowModality.WindowModal)
    espera.setMinimumDuration(0)
    espera.show()
    daemon.garantir(a_cada_iteracao=app.processEvents)
    espera.close()


def main() -> None:
    sys.excepthook = _erro_inesperado
    _carregar_env_do_executavel()  # estação: endereço do servidor (antes de tudo)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(icone_printgest())  # taskbar/barra de título (dev e pacote)
    aplicar_theme(app)

    if modo_estacao():
        _iniciar_modo_estacao(app)
        sys.exit(app.exec())

    _preparar_daemon(app)

    api = Api()
    app.aboutToQuit.connect(api.fechar)

    roteador = _Roteador(api)
    roteador.iniciar()
    sys.exit(app.exec())


# Referências fortes da fase de estação: janela, Api e roteador precisam
# sobreviver ao retorno das funções que os criam. `app.setProperty` NÃO serve
# (QVariant guarda o ponteiro C++ sem manter a referência Python — o GC
# destrói a janela e o Qt encerra a app quando a última fecha).
_ESTACAO: dict = {}


def _iniciar_modo_estacao(app: QApplication) -> None:
    """Estação: primeiro conecta ao servidor, depois login (sem serial)."""
    janela = ConexaoWindow()

    def conectar(endereco: str) -> None:
        api = Api(base_url=endereco)
        app.aboutToQuit.connect(api.fechar)
        roteador = _Roteador(api, estacao=True)
        roteador.iniciar()
        _ESTACAO["roteador"] = roteador
        _ESTACAO["api"] = api

    janela.conectado.connect(conectar)
    janela.saida.connect(app.quit)
    janela.show()
    _ESTACAO["janela"] = janela  # referência Python viva durante o exec()


if __name__ == "__main__":
    main()