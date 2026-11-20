"""Mede a geometria do sidebar em 1024×768 e 1366×768 (offscreen).

Uso:
    desktop/.venv/Scripts/python.exe scripts/medir_sidebar.py

Não altera dados nem abre janelas visíveis. Serve como evidência das
auditorias de altura/espaçamento do menu lateral.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "desktop"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
from PySide6.QtWidgets import QApplication, QScrollArea

# Evita chamadas de rede e modais: só queremos a geometria do menu.
import printgest.core.tarefas as tarefas


def _rodar_sem_rede(fn, on_ok, on_erro):
    try:
        on_ok({})
    except Exception:
        pass


tarefas.rodar = _rodar_sem_rede

from printgest.core.api import Api
from printgest.ui.tela_principal import TelaPrincipal
from printgest.ui.theme import aplicar_theme

_USUARIO_ADMIN = {"id": 1, "nome": "Ana", "login": "ana", "nivel_acesso": "admin"}


def _app() -> Api:
    api = Api(
        base_url="http://daemon.test",
        transport=httpx.MockTransport(lambda _r: httpx.Response(404, json={"detail": "off"})),
    )
    api.autenticar({"token": "tok", "usuario": _USUARIO_ADMIN})
    return api


def _medir(app: QApplication, largura: int, altura: int, fonte_maior: bool = False) -> None:
    principal = TelaPrincipal(
        _app(), usuario=_USUARIO_ADMIN, base_url="127.0.0.1:8000"
    )
    if fonte_maior:
        for botao in principal._botoes_menu:
            botao.setStyleSheet("font-size: 22px; padding: 7px 10px;")
        for grupo in principal._grupos_menu:
            grupo.setStyleSheet("font-size: 16px; padding: 10px 5px 4px 5px;")
    principal.show()
    app.processEvents()
    principal.resize(largura, altura)
    app.processEvents()

    scroll = principal._sidebar.findChild(QScrollArea, "menuScroll")
    conteudo = scroll.widget()
    ultimo = principal._btn_menu["consolidacao"]
    print(
        f"{largura}x{altura} fonte={'22px' if fonte_maior else 'padrao'}: "
        f"colapsada={principal._colapsada} "
        f"sidebar_largura={principal._sidebar.width()} "
        f"sidebar_altura={principal._sidebar.height()} "
        f"conteudo_altura={conteudo.sizeHint().height()} "
        f"scroll_max={scroll.verticalScrollBar().maximum()} "
        f"botoes_visiveis={sum(1 for b in principal._botoes_menu if b.isVisible())}/"
        f"{len(principal._botoes_menu)} "
        f"ultimo_item_y={ultimo.y()} h={ultimo.height()}"
    )
    principal.close()
    principal.deleteLater()
    app.processEvents()


def main() -> None:
    app = QApplication.instance() or QApplication([])
    aplicar_theme(app)
    _medir(app, 1366, 768)
    _medir(app, 1366, 768, fonte_maior=True)
    _medir(app, 1024, 768)


if __name__ == "__main__":
    main()
