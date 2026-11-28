# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-PrintGest-Commercial
import logging
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
from printgest.core.logging_app import configurar_logging, mascarar
from printgest.core.notificacao import mensagem_segura, titulo_erro
from printgest.core.sessao import carregar_sessao, salvar_sessao, limpar_sessao
from printgest.core.tarefas import rodar
from printgest.ui.ativacao import AtivacaoWindow
from printgest.ui.conexao import ConexaoWindow
from printgest.ui.login import LoginWindow
from printgest.ui.modoleitura import ModoLeituraWindow
from printgest.ui.tela_principal import TelaPrincipal
from printgest.ui.theme import aplicar_theme
from printgest.ui.widgets import icone_printgest

# Timeout para aguardar daemon estar pronto (segundos)
DAEMON_READY_TIMEOUT = 2.0


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
    except OSError as exc:
        logging.getLogger("printgest.desktop").warning(
            "Não foi possível ler %s: %s — usando variáveis de ambiente.",
            caminho,
            type(exc).__name__,
        )
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


def _aguardar_daemon_pronto(timeout: float = DAEMON_READY_TIMEOUT) -> bool:
    """Aguarda o daemon estar saudável por um breve período.
    
    Retorna True se o daemon estiver saudável, False caso contrário.
    Usado para garantir que a sessão persistente não tenta conectar
    antes que o daemon esteja totalmente inicializado.
    """
    import time
    inicio = time.monotonic()
    while time.monotonic() - inicio < timeout:
        if daemon.saude():
            return True
        time.sleep(0.1)
    return False


def _erro_inesperado(tipo: type, valor: BaseException, tb) -> None:
    """Protocolo 4: exceção não tratada é detalhada no arquivo de log."""
    import traceback

    logger = logging.getLogger("printgest.desktop")
    logger.error(
        "Erro não tratado no desktop | tipo=%s mensagem=%s",
        tipo.__name__, mascarar(str(valor)), exc_info=(tipo, valor, tb),
    )
    traceback.print_exception(tipo, valor, tb)
    try:
        QMessageBox.critical(
            None,
            "Erro inesperado",
            f"Ocorreu um erro inesperado.\n\n"
            f"{tipo.__name__}: {mensagem_segura(valor)}\n\n"
            "Os detalhes completos foram gravados em logs/printgest.log.",
        )
    except Exception as exc:
        logger.warning("Falha ao exibir diálogo de erro: %s", exc)


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
    
    **Sessão Persistente:** Quando há sessão salva localmente (após login
    anterior), o sistema pode abrir diretamente no dashboard sem repetir o
    login, exceto quando o usuário fizer logout ou o computador for reiniciado.
    """

    def __init__(self, api: Api, estacao: bool = False) -> None:
        self._api = api
        self._token: str | None = None
        self._janela: QWidget | None = None
        self._licenca_desabilitada = _licenca_desabilitada()
        self._estacao = estacao
        self._sessao_salva = False  # Flag para controlar se vem de sessão salva
        self._validando_licenca = False  # Flag anti-reentrância

    def iniciar(self) -> None:
        """Ponto de entrada: o serial precede o login (gate de instalação).

        Sessão persistente (regra de produto): login se repete apenas quando o
        **computador reinicia** (`sessao.tempo_boot` muda) ou o usuário clica em
        **Sair**. Fechar/abrir o programa, inatividade e reinício do daemon não
        pedem login de novo.
        """
        # Sessão salva (servidor e estação; dev não persiste).
        if not self._licenca_desabilitada:
            sessao = carregar_sessao()
            if sessao:
                self._sessao_salva = True
                self._token = sessao["token"]
                # `autenticar` espera o formato da resposta do login
                # (`{"token": ..., "usuario": {...}}`); passar o usuário
                # "achatado" quebrava a restauração da sessão com KeyError.
                self._api.autenticar(
                    {"token": sessao["token"], "usuario": sessao["usuario"]}
                )
                # O daemon pode estar acordando (Neon/cold start): espera
                # saúde antes do probe — um erro de transporte NÃO pode destruir
                # a sessão salva.
                _aguardar_daemon_pronto(10.0)
                # Valida o token no servidor (`/v1/auth/me` exige autenticação;
                # `/v1/licenca` não valida token e deixaria token morto passar).
                rodar(
                    self._api.validar_sessao,
                    on_ok=self._sessao_validada,
                    on_erro=self._falha_restauracao,
                )
                return

        # Fluxo normal (sem sessão salva ou modo desenvolvimento)
        if self._licenca_desabilitada or self._estacao:
            self._abrir_login()
            return
        self._verificar_licenca()

    def _sessao_validada(self, usuario: dict) -> None:
        """Token confirmado pelo servidor: segue para o dashboard."""
        if self._estacao:
            # Na estação a licença é do servidor (modo leitura chega como 423);
            # abre direto — sem tela de ativação/renovação local.
            self._abrir_dashboard(False)
            return
        rodar(
            lambda: self._api.situacao_licenca(self._token),
            on_ok=self._situacao_com_sessao,
            on_erro=self._sem_daemon,
        )

    def _falha_restauracao(self, msg: str) -> None:
        """Falha ao validar a sessão salva na abertura.

        Token recusado (401: sessão encerrada/revogada) ou bloqueio (423:
        excesso de tentativas, agora reforçado em toda requisição) → limpa e
        pede login. Erro de transporte (daemon caído/rede) → mantém a sessão e
        oferece tentar de novo — destruir a cópia aqui devolvia o usuário à
        tela de login a cada boot frio do daemon.
        """
        status = getattr(self._api, "ultimo_status", None)
        if status in (401, 423):
            self._sessao_invalida(msg, status)
            return
        self._sem_daemon(msg)

    def _situacao_com_sessao(self, sit: dict) -> None:
        """Trata a situação quando a sessão foi restaurada com sucesso."""
        status = sit["status"]
        if status == "nao_ativada":
            # Licença foi revogada ou reinstalação detectada: a sessão salva não
            # vale mais e a ativação acontece antes de qualquer autenticação.
            limpar_sessao()
            self._token = None
            self._api.encerrar_sessao()
            self._sessao_salva = False
            self._abrir_ativacao(sit, token=None, apos_ativacao=self._abrir_login)
        elif sit["modo_leitura"]:
            self._abrir_modo_leitura(sit)
        else:
            self._abrir_dashboard(False, sit=sit)

    def _sessao_invalida(self, msg: str, status: int | None = None) -> None:
        """A sessão salva está expirada/inválida/bloqueada - limpa e abre login."""
        limpar_sessao()
        self._token = None
        self._api.encerrar_sessao()
        self._sessao_salva = False
        detalhe = (
            mensagem_segura(msg)
            if status == 423
            else "Sua sessão expirou ou foi encerrada em outro dispositivo."
        )
        QMessageBox.information(
            None,
            titulo_erro(status, msg, "Sessão encerrada"),
            f"{detalhe}\n\nPor favor, faça login novamente.",
        )
        if self._licenca_desabilitada or self._estacao:
            self._abrir_login()
        else:
            self._verificar_licenca()

    # ------------------------------------------------------------------ ajuda

    def _fechar_janela(self) -> None:
        if self._janela is not None:
            self._janela.close()
            self._janela = None

    def _abrir(self, janela: QWidget) -> None:
        self._fechar_janela()
        self._janela = janela
        # Maximizar a janela ao abrir, respeitando a barra do Windows
        self._janela.showMaximized()

    # ---------------------------------------------------------------- licença

    def _verificar_licenca(self) -> None:
        """Consulta a situação sem sessão: o serial precede o login.

        `GET /v1/licenca` e `POST /v1/licenca/ativar` são liberados pelo
        Local API Service justamente para permitir a ativação antes de haver
        usuário autenticado.
        """
        self._validando_licenca = True
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

        # Sessão persistente (servidor e estação): repetir login só ao reiniciar
        # o computador ou no "Sair". Dev (licença desabilitada) não persiste.
        if not self._licenca_desabilitada:
            salvar_sessao(dados["token"], dados["usuario"])
        
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
            f"{mensagem_segura(msg)}\n\nVerifique se o daemon (127.0.0.1:8000) "
            "está em execução e tente novamente."
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
    
    def _limpar_e_logout(self) -> None:
        """Limpa a sessão e abre a tela de login (usado quando usuário sai)."""
        limpar_sessao()
        self._sessao_salva = False
        self._abrir_login()

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
        janela = AtivacaoWindow(
            self._api, token=token, contrato=contrato, situacao=sit
        )
        janela.ativada.connect(apos_ativacao or self._abrir_login)
        janela.saida.connect(QApplication.instance().quit)
        self._abrir(janela)

    def _abrir_modo_leitura(self, sit: dict) -> None:
        janela = ModoLeituraWindow(self._api, token=self._token, situacao=sit)
        janela.renovada.connect(lambda: self._abrir_dashboard(False))
        janela.consulta.connect(lambda: self._abrir_dashboard(True))
        # Licença revogada/expirada: renovar não recupera — a saída é inserir a
        # licença nova (o `/v1/licenca/ativar` é liberado no modo leitura).
        janela.reativar.connect(
            lambda: self._abrir_ativacao(
                sit,
                token=self._token,
                apos_ativacao=lambda: self._abrir_dashboard(False),
            )
        )
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
            estacao=self._estacao,
        )
        # Quando o usuário faz logout, limpar a sessão salva
        principal.solicitado_logout.connect(self._limpar_e_logout)
        self._abrir(principal)


def _preparar_daemon(app: QApplication) -> None:
    """Instalação empacotada: sobe o Local API Service antes do fluxo normal.

    O daemon se conecta ao Neon Database (não há mais initdb local).
    O diálogo mantém o usuário informado em vez de uma janela congelada.
    Sem nada para subir (dev) a chamada é uma sondagem rápida.
    """
    if daemon.saude():
        return
    if daemon.caminho_do_backend() is None:
        return
    espera = QProgressDialog(
        "Preparando conexão com Neon Database...\nA primeira execução pode levar alguns segundos.",
        None,
        0,
        0,
    )
    espera.setWindowTitle(APP_NAME)
    espera.setWindowModality(Qt.WindowModality.WindowModal)
    espera.setMinimumDuration(0)
    espera.show()
    pronto = daemon.garantir(a_cada_iteracao=app.processEvents)
    espera.close()
    if not pronto:
        # Antes o retorno era descartado e o boot seguia como se nada tivesse
        # acontecido — o primeiro erro virava um diálogo genérico de licença.
        logging.getLogger("printgest.desktop").error(
            "Falha ao iniciar o Local API Service no boot (ver logs/printgest.log)."
        )
        QMessageBox.warning(
            None,
            "Serviço local",
            "Não foi possível iniciar o serviço local do PrintGest.\n\n"
            "Consulte logs/printgest.log. O programa será aberto, mas as "
            "operações podem falhar até que o serviço seja restabelecido.",
        )


def main() -> None:
    configurar_logging()  # antes do QApplication: captura falhas de startup
    logging.getLogger("printgest.desktop").info("PrintGest ERP v%s iniciando", __version__)
    sys.excepthook = _erro_inesperado
    _carregar_env_do_executavel()  # estação: endereço do servidor (antes de tudo)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(icone_printgest())  # taskbar/barra de título (dev e pacote)
    aplicar_theme(app)

    if modo_estacao():
        _iniciar_modo_estacao(app)
    else:
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
    janela.showMaximized()  # Maximizar a janela de conexão
    _ESTACAO["janela"] = janela  # referência Python viva durante o exec()


if __name__ == "__main__":
    main()