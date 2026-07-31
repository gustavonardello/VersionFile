# -*- mode: python ; coding: utf-8 -*-
"""
Spec do PyInstaller para o VersionFile (modo onedir).

    pyinstaller --noconfirm VersionFile.spec
    # saída: dist/VersionFile/ (pasta com VersionFile.exe + DLLs)

Os arquivos em `datas` são lidos em tempo de execução via `base_path()`, que
aponta para o diretório do executável quando congelado em modo onedir.
Esquecer qualquer um deles gera um .exe que abre e quebra depois:

  - config/themes.json : `_bootstrap()` em main.py copia este arquivo para a
                         pasta de dados na primeira execução. Sem ele o editor
                         fica sem paleta de cores.
  - icone.ico          : usado por main.py (ícone do app) e main_window.py.
  - logo.png           : logo no topo do painel da árvore (tree_panel.py). A
                         leitura é protegida por `if exists()`, então a falta
                         dele não quebra o app — a logo só some, sem aviso.

Os dados mutáveis do usuário (banco, configs editados) NÃO ficam aqui — vivem
em %LOCALAPPDATA%\VersionFile, resolvido por `data_path()`.
"""

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config/themes.json", "config"),
        ("icone.ico", "."),
        ("logo.png", "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VersionFile",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["icone.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VersionFile",
)
