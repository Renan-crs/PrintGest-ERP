# -*- mode: python ; coding: utf-8 -*-
# Especificação PyInstaller do Local API Service (backend) -> PrintGestAPI.exe
#
# Build via scripts/empacotar.ps1 (invoca este spec a partir de installer/).
# onedir (não onefile): startup a frio importa módulos direto do disco — a
# primeira execução da instalação já roda initdb do PostgreSQL embarcado.
#
# `datas` embarca o que o runtime carrega fora de imports:
#   - alembic.ini + alembic/  -> migrations aplicadas no primeiro startup
#     (app/core/migrations.py resolve ambos a partir de sys._MEIPASS).
# console=False: o daemon roda oculto; o log vai para logs/printgest-api.log
# (anexado pelo run_server.py) e o desktop o sobe sem janela.

import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(RAIZ, "backend")

a = Analysis(
    [os.path.join(BACKEND, "run_server.py")],
    pathex=[BACKEND],
    binaries=[],
    datas=[
        (os.path.join(BACKEND, "alembic.ini"), "."),
        (os.path.join(BACKEND, "alembic"), "alembic"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # Migrations no exe congelado rodam pela API Python (não há
        # `python -m alembic`); o env.py das versões importa estes pacotes.
        "alembic",
        "alembic.config",
        "alembic.command",
        "alembic.runtime.migration",
        "alembic.script",
        "mako",
        "mako.template",
        "psycopg",
        "psycopg.pq",
        "sqlalchemy.dialects.postgresql",
    ],
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
    name="PrintGestAPI",
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PrintGestAPI",
)
