from pathlib import Path
import json

from seshat_tts.config import AppConfig, Rect, load_config, save_config


def test_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = AppConfig(
        monitor_index=2,
        hotkey="ctrl+shift+d",
        capture_region_hotkey="ctrl+shift+r",
        stop_hotkey="ctrl+shift+s",
        dialogue_rect=Rect(left=1, top=2, width=3, height=4),
        tesseract_cmd="C:/Tesseract/tesseract.exe",
        voice_source="custom-wav",
        default_voice="alba",
        voice_path="voice.mp3",
        language="english",
        quantize_tts=True,
        volume_gain=1.75,
        last_text="hello",
    )

    save_config(config, path)

    assert load_config(path) == config


def test_load_config_removes_old_region_metadata_from_last_text(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "last_text": "Capture region: 85,51 628x84\nText region: 85,44 633x77\n\nA line to read."
            }
        ),
        encoding="utf-8",
    )

    assert load_config(path).last_text == "A line to read."


def test_load_config_reads_llm_settings(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "llm_enabled": True,
                "llm_base_url": "http://127.0.0.1:11434/v1",
                "llm_api_key": "local",
                "llm_model": "unsloth-local",
                "llm_timeout": 1.5,
                "llm_max_tokens": 64,
                "llm_disable_thinking": False,
                "llm_image_extraction": True,
                "llm_system_prompt": "clean this",
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.llm_enabled is True
    assert config.llm_base_url == "http://127.0.0.1:11434/v1"
    assert config.llm_api_key == "local"
    assert config.llm_model == "unsloth-local"
    assert config.llm_timeout == 1.5
    assert config.llm_max_tokens == 64
    assert config.llm_disable_thinking is False
    assert config.llm_image_extraction is True
    assert config.llm_system_prompt == "clean this"


def test_load_config_forces_english_language(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "french"}), encoding="utf-8")

    assert load_config(path).language == "english"
