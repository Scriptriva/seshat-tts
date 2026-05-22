from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .tesseract import tesseract_help_message


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    image = ImageOps.expand(image, border=12, fill=(0, 0, 0))
    gray = ImageOps.grayscale(image)
    enlarged = gray.resize((gray.width * 2, gray.height * 2), Image.Resampling.LANCZOS)
    contrast = ImageEnhance.Contrast(enlarged).enhance(2.2)
    sharpened = contrast.filter(ImageFilter.SHARPEN)
    return sharpened.point(lambda pixel: 255 if pixel > 145 else 0)


def image_to_lines(image: Image.Image, tesseract_cmd: str = "") -> list[str]:
    import pytesseract
    from pytesseract import TesseractNotFoundError

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    tessdata = _tessdata_dir(tesseract_cmd)
    if tessdata is not None:
        os.environ["TESSDATA_PREFIX"] = str(tessdata)
    config = "--psm 6 --oem 3"
    try:
        text = pytesseract.image_to_string(image, lang="eng", config=config)
    except TesseractNotFoundError as exc:
        raise RuntimeError(tesseract_help_message()) from exc
    return [normalize_line(line) for line in text.splitlines() if normalize_line(line)]


def normalize_line(line: str) -> str:
    import re

    line = re.sub(r"\s+", " ", line).strip()
    line = line.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    return line


def extract_text_from_lines(lines: list[str]) -> str:
    return " ".join(lines).strip()


def extract_ocr_text(image: Image.Image, tesseract_cmd: str = "") -> str:
    processed = preprocess_for_ocr(image)
    return extract_text_from_lines(image_to_lines(processed, tesseract_cmd))


def _tessdata_dir(tesseract_cmd: str) -> Path | None:
    if not tesseract_cmd:
        return None
    tessdata = Path(tesseract_cmd).resolve().parent / "tessdata"
    if tessdata.exists():
        return tessdata
    return None
