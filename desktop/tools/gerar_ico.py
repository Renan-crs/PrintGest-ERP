"""Gera `assets/printgest.ico` a partir do ícone vetorial oficial.

O Windows precisa de um .ico para o executável (PyInstaller `icon=`) e para o
instalador (Inno `SetupIconFile`). Este script rasteriza o SVG nos tamanhos
padrão usando o próprio Qt (mesma renderização do app) e empacota com Pillow
(ferramenta de build; não vira dependência de runtime).

Uso:
    desktop\\.venv\\Scripts\\python.exe desktop\\tools\\gerar_ico.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "printgest" / "ui" / "assets"
SVG = ASSETS / "printgest-icone.svg"
ICO = ASSETS / "printgest.ico"
TAMANHOS = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PIL import Image
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    icone = QIcon(str(SVG))
    if icone.isNull():
        raise SystemExit(f"ícone não carregou: {SVG}")

    imagens: list = []
    for tamanho in TAMANHOS:
        pm = icone.pixmap(QSize(tamanho, tamanho))
        img = Image.frombytes(
            "RGBA", (pm.width(), pm.height()), pm.toImage().convertToFormat(
                pm.toImage().Format.Format_RGBA8888
            ).constBits().tobytes()
        )
        # Qt entrega BGRA na memória em little-endian; RGBA8888 já é ordem certa
        imagens.append((img, tamanho))
        print(f"rasterizado {tamanho}px")

    # O ICO usa a maior como base; Pillow gera as demais do mesmo buffer.
    base = max(imagens, key=lambda par: par[1])[0]
    base.save(
        ICO,
        format="ICO",
        sizes=[(t, t) for _, t in imagens],
    )
    print(f"OK: {ICO} ({ICO.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
