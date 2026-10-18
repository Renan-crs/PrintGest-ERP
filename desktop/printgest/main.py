import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from printgest import APP_NAME, __version__
from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.ativacao import AtivacaoWindow
from printgest.ui.login import LoginWindow
from printgest.ui.modoleitura import ModoLeituraWindow
from printgest.ui.tela_principal import TelaPrincipal
from printgest.ui.theme import aplicar_theme


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
    """Fluxo de entrada (§3.1): Login → licença válida? → Ativação/Modo Leitura/Dashboard.

    Com `PRINTGEST_LICENCA_DESABILITADA=true`, a etapa de licença é pulada e o
    login abre direto o sistema (desenvolvimento).
    """

    def __init__(self, api: Api) -> None:
        self._api = api
        self._token: str | None = None
        self._janela: QWidget | None = None
        self._licenca_desabilitada = _licenca_desabilitada()

    def iniciar(self) -> None:
        self._abrir_login()

    # ------------------------------------------------------------------ ajuda

    def _fechar_janela(self) -> None:
        if self._janela is not None:
            self._janela.close()
            self._janela = None

    def _abrir(self, janela: QWidget) -> None:
        self._fechar_janela()
        self._janela = janela
        self._janela.show()

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
        if caixa.exec() == 0 and self._token:
            rodar(
                lambda: self._api.situacao_licenca(self._token),
                on_ok=self._situacao,
                on_erro=self._sem_daemon,
            )
        else:
            QApplication.instance().quit()

    def _situacao(self, sit: dict) -> None:
        status = sit["status"]
        if status == "nao_ativada":
            self._abrir_ativacao(sit)
        elif sit["modo_leitura"]:
            self._abrir_modo_leitura(sit)
        else:
            self._abrir_dashboard(False, sit=sit)

    # ---------------------------------------------------------------- telas

    def _abrir_ativacao(self, sit: dict) -> None:
        janela = AtivacaoWindow(
            self._api, token=self._token, cnpj_atual=sit.get("cnpj")
        )
        janela.ativada.connect(lambda: self._abrir_dashboard(False))
        janela.saida.connect(QApplication.instance().quit)
        self._abrir(janela)

    def _abrir_modo_leitura(self, sit: dict) -> None:
        janela = ModoLeituraWindow(
            self._api, token=self._token, cnpj=sit.get("cnpj"), situacao=sit
        )
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


def main() -> None:
    sys.excepthook = _erro_inesperado
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    aplicar_theme(app)

    api = Api()
    app.aboutToQuit.connect(api.fechar)

    roteador = _Roteador(api)
    roteador.iniciar()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()