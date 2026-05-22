# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path.cwd()

a = Analysis(
    ["scripts/pyinstaller_entry.py"],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=(
        ([(str(ROOT / "resources"), "resources")] if (ROOT / "resources").exists() else [])
        + ([(str(ROOT / "LICENSE"), ".")] if (ROOT / "LICENSE").exists() else [])
        + ([(str(ROOT / "THIRD_PARTY_NOTICES.md"), ".")] if (ROOT / "THIRD_PARTY_NOTICES.md").exists() else [])
    ),
    hiddenimports=[
        "pytesseract",
        "mss",
        "keyboard",
        "sounddevice",
        "imageio_ffmpeg",
        "openai",
        "win32gui",
        "win32con",
        "win32ui",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pocket_tts",
        "torch",
        "torchaudio",
        "torchvision",
        "torchao",
        "xformers",
        "triton",
        "bitsandbytes",
        "pandas",
        "scipy",
        "matplotlib",
        "pyarrow",
        "numba",
        "llvmlite",
        "pytest",
        "IPython",
        "jupyter",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="seshat-tts",
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
    icon=str(ROOT / "resources" / "seshat-tts.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="seshat-tts",
)
