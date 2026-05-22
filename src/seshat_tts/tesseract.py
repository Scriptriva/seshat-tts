from __future__ import annotations

import shutil
from pathlib import Path

from .resources import resource_path


COMMON_TESSERACT_PATHS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)


def find_tesseract() -> str:
    bundled = resource_path("tesseract/tesseract.exe")
    if bundled.exists():
        return str(bundled)
    from_path = shutil.which("tesseract")
    if from_path:
        return from_path
    for path in COMMON_TESSERACT_PATHS:
        if path.exists():
            return str(path)
    return ""


def tesseract_help_message() -> str:
    return (
        "Tesseract OCR is not installed or the executable is not configured. "
        "Install it with `winget install UB-Mannheim.TesseractOCR`, then restart the app, "
        "or select tesseract.exe in the GUI."
    )
