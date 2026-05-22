from pathlib import Path
import queue

from seshat_tts import tts


def test_prepared_audio_prompt_leaves_wav_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "voice.wav"
    source.write_bytes(b"wav")

    assert tts._prepared_audio_prompt_path(source, "english", queue.Queue()) == source


def test_prepared_audio_prompt_converts_mp3_once(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "voice.mp3"
    source.write_bytes(b"mp3")
    cache = tmp_path / "cache"
    calls: list[tuple[Path, Path]] = []

    monkeypatch.setattr(tts, "VOICE_CACHE_DIR", cache)

    def fake_convert(input_path: Path, output_path: Path) -> None:
        calls.append((input_path, output_path))
        output_path.write_bytes(b"wav")

    monkeypatch.setattr(tts, "_convert_mp3_to_wav", fake_convert)

    first = tts._prepared_audio_prompt_path(source, "english", queue.Queue())
    second = tts._prepared_audio_prompt_path(source, "english", queue.Queue())

    assert first == second
    assert first.suffix == ".wav"
    assert first.exists()
    assert calls == [(source, first)]
