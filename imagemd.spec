# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Recolectar automáticamente todos los recursos de ttkbootstrap (temas, fuentes, etc.)
datas, binaries, hiddenimports = collect_all('ttkbootstrap')

# Asegurar que se incluyan dependencias críticas que a veces el análisis estático pierde
hiddenimports += [
    'PIL', 
    'piexif', 
    'ffmpeg', 
    'tkinter', 
    'tkinter.filedialog',
    'tkinter.messagebox'
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas, 
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ImageMD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # Desactiva la consola (GUI mode)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
