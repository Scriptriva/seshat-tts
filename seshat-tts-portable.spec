# -*- mode: python ; coding: utf-8 -*-

import os
import shutil
from pathlib import Path

ROOT = Path.cwd()

datas = []
binaries = []

resources = ROOT / "resources"
if resources.exists():
    datas.append((str(resources), "resources"))

license_file = ROOT / "LICENSE"
if license_file.exists():
    datas.append((str(license_file), "."))

third_party_notices = ROOT / "THIRD_PARTY_NOTICES.md"
if third_party_notices.exists():
    datas.append((str(third_party_notices), "."))

tesseract_dir = Path(os.environ.get("SESHAT_TESSERACT_DIR", r"C:\Program Files\Tesseract-OCR"))
if tesseract_dir.exists():
    datas.append((str(tesseract_dir), "tesseract"))

for tool_name in ("uvx.exe", "uv.exe"):
    tool = shutil.which(tool_name)
    if tool:
        binaries.append((tool, "tools"))

a = Analysis(
    ["scripts/pyinstaller_entry.py"],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
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
    a.binaries,
    a.datas,
    [],
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
