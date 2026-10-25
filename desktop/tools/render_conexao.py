"""Renderiza a tela Conectar ao Servidor (modo Estação) em PNG offscreen.

Uso:
    desktop\\.venv\\Scripts\\python.exe desktop\\tools\\render_conexao.py [inicial|erro] [largura altura] [escala]

Gera `conexao_<estado>_<WxH>@<escala>_preview.png` na raiz do desktop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx  # noqa: E402
from PySide6.QtCore import QSettings, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import printgest.ui.conexao as mod_conexao  # noqa: E402
from printgest.ui.conexao import ConexaoWindow  # noqa: E402
from printgest.ui.theme import aplicar_theme  # noqa: E402

ESTADO = (sys.argv[1] if len(sys.argv) > 1 else "inicial").strip().lower()
LARGURA = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
ALTURA = int(sys.argv[3]) if len(sys.argv) > 3 else 720
ESCALA = sys.argv[4] if len(sys.argv) > 4 else "100"
os.environ["QT_SCALE_FACTOR"] = str(int(ESCALA) / 100)


class _ApiFake:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def testar_comunicacao(self) -> bool:
        return ESTADO != "erro"

    def fechar(self) -> None:
        pass


def main() -> None:
    app = QApplication(sys.argv[:1])
    aplicar_theme(app)
    original = mod_conexao.Api
    mod_conexao.Api = _ApiFake  # sem rede: estado define a resposta
    ini = Path(os.environ.get("TEMP", ".")) / "printgest_conexao_preview.ini"
    ajustes = QSettings(str(ini), QSettings.Format.IniFormat)
    tela = ConexaoWindow(ajustes=ajustes)
    mod_conexao.Api = original
    tela._campo.setText("192.168.0.10:8000")
    if ESTADO == "erro":
        tela._erro.setText(
            "Não foi possível conectar — confira o endereço e se o servidor "
            "está ligado."
        )
    tela.resize(LARGURA, ALTURA)
    tela.show()

    destino = (
        Path(__file__).resolve().parents[1]
        / f"conexao_{ESTADO}_{LARGURA}x{ALTURA}@{ESCALA}_preview.png"
    )

    def capturar() -> None:
        tela.grab().save(str(destino))
        print(f"salvo: {destino}")
        app.quit()

    QTimer.singleShot(300, capturar)
    app.exec()


if __name__ == "__main__":
    main()
