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
# console=True + CREATE_NO_WINDOW: apps PyInstaller windowed travam no startup
# porque uvicorn/logging escrevem em um stderr que não existe (sem console).
# O desktop sobe este exe com CREATE_NO_WINDOW | DETACHED_PROCESS — o console
# nunca aparece para o usuário; direto do Explorador ele aparece (debug).

import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(RAIZ, "backend")
ICONE = os.path.join(RAIZ, "desktop", "printgest", "ui", "assets", "printgest.ico")

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
        # Upload de arte (File/multipart): o starlette.formparsers importa
        # python_multipart em try/except ImportError — o PyInstaller trata
        # como opcional e nao empacota; sem ele o exe falha nas rotas com
        # File/Form (e no startup, no registro das rotas).
        "python_multipart",
        "python_multipart.multipart",
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
    console=True,
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
    name="PrintGestAPI",
)
