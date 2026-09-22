import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from printgest import APP_NAME, __version__
from printgest.core.api import Api
from printgest.core.tarefas import rodar
from printgest.ui.ativacao import AtivacaoWindow
from printgest.ui.dashboard import DashboardWindow
from printgest.ui.login import LoginWindow
from printgest.ui.modoleitura import ModoLeituraWindow
from printgest.ui.theme import aplicar_theme


class _Roteador:
    """Fluxo de entrada (§3.1): Login → licença válida? → Ativação/Modo Leitura/Dashboard."""

    def __init__(self, api: Api) -> None:
        self._api = api
        self._token: str | None = None
        self._janela: QWidget | None = None

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
            self._abrir_dashboard(False)

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
            self._api, token=self._token, cnpj=sit.get("cnpj")
        )
        janela.renovada.connect(lambda: self._abrir_dashboard(False))
        janela.consulta.connect(lambda: self._abrir_dashboard(True))
        janela.saida.connect(QApplication.instance().quit)
        self._abrir(janela)

    def _abrir_dashboard(self, modo_leitura: bool) -> None:
        self._abrir(DashboardWindow(modo_leitura=modo_leitura))


def main() -> None:
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