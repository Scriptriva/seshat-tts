from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .tesseract import find_tesseract


APP_DIR = Path.home() / ".seshat-tts"
CONFIG_PATH = APP_DIR / "config.json"


@dataclass(slots=True)
class Rect:
    left: int = 0
    top: int = 25
    width: int = 720
    height: int = 305


@dataclass(slots=True)
class AppConfig:
    capture_mode: str = "monitor"
    monitor_index: int = 1
    window_title: str = ""
    hotkey: str = "ctrl+alt+n"
    capture_region_hotkey: str = "ctrl+alt+r"
    stop_hotkey: str = "ctrl+alt+s"
    dialogue_rect: Rect = field(default_factory=Rect)
    tesseract_cmd: str = field(default_factory=find_tesseract)
    voice_source: str = "default"
    default_voice: str = "alba"
    custom_voice_name: str = ""
    voice_path: str = ""
    language: str = "english"
    quantize_tts: bool = False
    volume_gain: float = 1.0
    tts_backend: str = "uvx-server"
    tts_host: str = "localhost"
    tts_port: int = 8000
    llm_enabled: bool = False
    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_api_key: str = ""
    llm_model: str = "current"
    llm_timeout: float = 5.0
    llm_max_tokens: int = 256
    llm_disable_thinking: bool = True
    llm_image_extraction: bool = False
    llm_system_prompt: str = (
        "Clean OCR text for text-to-speech. Return only the corrected text. "
        "Do not explain, add commentary, summarize, or change the meaning."
    )
    last_text: str = ""


def _rect_from_dict(value: dict[str, Any] | None) -> Rect:
    if not value:
        return Rect()
    return Rect(**{field: int(value.get(field, getattr(Rect(), field))) for field in Rect.__dataclass_fields__})


def _clean_last_text(value: Any) -> str:
    lines = str(value or "").splitlines()
    cleaned = [
        line
        for line in lines
        if not line.strip().casefold().startswith(("capture region:", "text region:"))
    ]
    return "\n".join(cleaned).strip()


def _tesseract_from_config(value: Any) -> str:
    detected = find_tesseract()
    if getattr(sys, "frozen", False) and detected:
        return detected
    return str(value or detected)


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    if not path.exists():
        return AppConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig(
        capture_mode=str(data.get("capture_mode", "monitor")),
        monitor_index=int(data.get("monitor_index", 1)),
        window_title=str(data.get("window_title", "")),
        hotkey=str(data.get("hotkey", "ctrl+alt+n")),
        capture_region_hotkey=str(data.get("capture_region_hotkey", "ctrl+alt+r")),
        stop_hotkey=str(data.get("stop_hotkey", "ctrl+alt+s")),
        dialogue_rect=_rect_from_dict(data.get("dialogue_rect")),
        tesseract_cmd=_tesseract_from_config(data.get("tesseract_cmd")),
        voice_source=str(data.get("voice_source", "default")),
        default_voice=str(data.get("default_voice", "alba")),
        custom_voice_name=str(data.get("custom_voice_name", "")),
        voice_path=str(data.get("voice_path", "")),
        language="english",
        quantize_tts=bool(data.get("quantize_tts", False)),
        volume_gain=float(data.get("volume_gain", 1.0)),
        tts_backend=str(data.get("tts_backend", "uvx-server")),
        tts_host=str(data.get("tts_host", "localhost")),
        tts_port=int(data.get("tts_port", 8000)),
        llm_enabled=bool(data.get("llm_enabled", False)),
        llm_base_url=str(data.get("llm_base_url", "http://127.0.0.1:8000/v1")),
        llm_api_key=str(data.get("llm_api_key", "")),
        llm_model=str(data.get("llm_model", "unsloth")),
        llm_timeout=float(data.get("llm_timeout", 5.0)),
        llm_max_tokens=int(data.get("llm_max_tokens", 256)),
        llm_disable_thinking=bool(data.get("llm_disable_thinking", True)),
        llm_image_extraction=bool(data.get("llm_image_extraction", False)),
        llm_system_prompt=str(
            data.get(
                "llm_system_prompt",
                AppConfig.__dataclass_fields__["llm_system_prompt"].default,
            )
        ),
        last_text=_clean_last_text(data.get("last_text", "")),
    )


def save_config(config: AppConfig, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
