# -*- mode: python ; coding: utf-8 -*-
# Especificação PyInstaller do desktop (PySide6) -> PrintGest.exe
#
# Build via scripts/empacotar.ps1 (invoca este spec a partir de installer/).
# onedir: o Qt carrega plugins (plataformas, estilos, imagens) do disco.
# `datas` embarca os ícones SVG do tema — theme.py resolve os caminhos a
# partir de __file__, que no exe aponta para dentro do bundle.
# console=False: aplicação de janela; o log do daemon fica em
# {app}\PrintGestAPI\logs\printgest-api.log.

import os

RAIZ = os.path.abspath(os.path.join(SPECPATH, ".."))
DESKTOP = os.path.join(RAIZ, "desktop")
ICONE = os.path.join(DESKTOP, "printgest", "ui", "assets", "printgest.ico")

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
    hiddenimports=[
        "printgest.ui.widgets",
        "printgest.ui.ativacao",
        "printgest.ui.login",
        "printgest.ui.conexao",
        "printgest.ui.tela_principal",
        "printgest.ui.modulos.os",
        "printgest.ui.modulos.venda_balcao",
        "printgest.ui.modulos.projetos",
        "printgest.ui.modulos.fiscal",
        "printgest.ui.modulos.financeiro",
        "printgest.ui.modulos.cotacoes",
        "printgest.ui.modulos.agendamento",
        "printgest.ui.modulos.clientes",
        "printgest.ui.modulos.categorias",
        "printgest.ui.modulos.fornecedores",
        "printgest.ui.modulos.estoque",
        "printgest.ui.modulos.configuracao",
        "printgest.ui.modulos.em_construcao",
        "printgest.ui.modulos.relatorios",
        "printgest.core.api",
        "printgest.core.daemon",
        "printgest.core.tarefas",
        "printgest.core.sessao",
        "printgest.core.dominio",
        "printgest.core.rbac",
        "printgest.core.catalogos",
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
