# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

PROJECT_ROOT = Path(SPECPATH).resolve().parents[1]
ICON_PATH = PROJECT_ROOT / "build" / "windows" / "FECArcade.ico"
VERSION_PATH = PROJECT_ROOT / "build" / "windows" / "version_info.txt"

mediapipe_datas = collect_data_files("mediapipe")
mediapipe_binaries = collect_dynamic_libs("mediapipe")

datas = [
    (str(PROJECT_ROOT / "imagem_geral.jpeg"), "."),
    (str(PROJECT_ROOT / "logo.png"), "."),
    (str(PROJECT_ROOT / "PressStart2P.ttf"), "."),
    (str(PROJECT_ROOT / "Fruit Ninja" / "nose_fruit_ninja.py"), "Fruit Ninja"),
    (str(PROJECT_ROOT / "Fruit Ninja" / "sprites"), "Fruit Ninja/sprites"),
    (str(PROJECT_ROOT / "nose_flappy" / "nose_flappy.py"), "nose_flappy"),
    (str(PROJECT_ROOT / "nose_flappy" / "sprites"), "nose_flappy/sprites"),
    (str(PROJECT_ROOT / "catch_fruit_game" / "game.py"), "catch_fruit_game"),
    (str(PROJECT_ROOT / "catch_fruit_game" / "assets"), "catch_fruit_game/assets"),
    (str(PROJECT_ROOT / "nosebird" / "main.py"), "nosebird"),
    (str(PROJECT_ROOT / "nosebird" / "entities.py"), "nosebird"),
    (str(PROJECT_ROOT / "nosebird" / "settings.py"), "nosebird"),
    (str(PROJECT_ROOT / "nosebird" / "tracker.py"), "nosebird"),
    (str(PROJECT_ROOT / "nosebird" / "sprites"), "nosebird/sprites"),
]
datas += mediapipe_datas

hiddenimports = [
    # Menus compartilhados importados pelos jogos (que entram como dados, não
    # como código analisado pelo PyInstaller)
    "game_menu",
    "cv2",
    "google.protobuf",
    "mediapipe",
    "mediapipe.python.solutions.face_mesh",
    "numpy",
]

analysis = Analysis(
    [str(PROJECT_ROOT / "app.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=mediapipe_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jax",
        "jaxlib",
        "notebook",
        "pandas",
        "pyarrow",
        "pytest",
        "scipy",
        "streamlit",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="FECArcade",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH),
    version=str(VERSION_PATH),
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="FECArcade",
)
