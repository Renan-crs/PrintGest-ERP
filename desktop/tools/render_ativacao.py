"""Renderiza a tela de ativação (serial) para PNG sem abrir janela real.

Uso:
    desktop\\.venv\\Scripts\\python.exe desktop\\tools\\render_ativacao.py [c|b]

Gera `ativacao_<contrato>.png` na raiz do desktop. Serve para inspecionar o
layout da tela exibida na instalação (antes do login).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from printgest.core.api import Api  # noqa: E402
from printgest.ui.ativacao import AtivacaoWindow  # noqa: E402
from printgest.ui.theme import aplicar_theme  # noqa: E402

CONTRATO = (sys.argv[1] if len(sys.argv) > 1 else "c").strip().lower()
if CONTRATO not in {"c", "b"}:
    raise SystemExit("contrato inválido: use 'c' ou 'b'")


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    return httpx.Response(404, json={"detail": "x"})


def main() -> None:
    app = QApplication(sys.argv[:1])
    aplicar_theme(app)
    api = Api(base_url="http://daemon.test", transport=httpx.MockTransport(handler))
    tela = AtivacaoWindow(api, token=None, contrato=CONTRATO)
    tela.resize(1100, 720)
    tela.show()

    destino = (
        Path(__file__).resolve().parents[1] / f"ativacao_{CONTRATO}_preview.png"
    )

    def capturar() -> None:
        tela.grab().save(str(destino))
        print(f"salvo: {destino}")
        app.quit()

    QTimer.singleShot(800, capturar)
    app.exec()


if __name__ == "__main__":
    main()
