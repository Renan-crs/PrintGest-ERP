# -*- mode: python ; coding: utf-8 -*-
# Especificação PyInstaller do desktop (PySide6) -> PrintGest.exe
#
# Build via scripts/empacotar.ps1 (invoca este spec a partir de installer/).
# onedir: o Qt carrega plugins (plataformas, estilos, imagens) do disco.
# `datas` embarca os ícones SVG do tema — theme.py resolve os caminhos a
# partir de __file__, que no exe aponta para dentro do bundle.
# console=False: aplicação de janela; o log do daemon fica em
# {app}\PrintGestAPI\logs\printgest-api.log.
#
# IMPORTANTE (v0.4.0): não listar hiddenimports à mão. A lista manual já
# ficou desatualizada e gerou `NameError: name 'estado_primario' is not
# defined` no executável instalado (o código empacotado era de um build
# antigo). Agora coletamos TODOS os submódulos de `printgest`
# automaticamente, então qualquer módulo novo entra no bundle sem edição.

import os
import sys

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
DESKTOP = os.path.join(RAIZ, "desktop")
ICONE = os.path.join(DESKTOP, "printgest", "ui", "assets", "printgest.ico")

# collect_submodules precisa do pacote importável neste ponto do spec.
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

from PyInstaller.utils.hooks import collect_submodules

# `desktop/printgest/ui/widgets.py` é um MÓDULO, mas existe também um
# diretório `ui/widgets/` sem __init__.py (arquivo órfão atualizacao.py).
# Os submodules desse diretório não são importáveis (colidem com o módulo)
# e não são usados por ninguém — ficam fora para não poluir a análise.
hiddenimports = [
    modulo
    for modulo in collect_submodules("printgest")
    if not modulo.startswith("printgest.ui.widgets.")
]
hiddenimports.append("printgest.ui.widgets")

a = Analysis(
    [os.path.join(DESKTOP, "main.py")],
    pathex=[DESKTOP],
    binaries=[],
    datas=[
        (
            os.path.join(DESKTOP, "printgest", "ui", "assets"),
            os.path.join("printgest", "ui", "assets"),
        ),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PrintGest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICONE,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PrintGest",
)
