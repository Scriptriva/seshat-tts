from __future__ import annotations

import collections
import functools
import hashlib
import http.server
import importlib
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import numpy as np
import requests
import sounddevice as sd

from .resources import resource_path
from .voices import safe_voice_slug


VOICE_CACHE_DIR = Path.home() / ".seshat-tts" / "voices"


class PocketTTSStreamer:
    def __init__(
        self,
        voice_path: str | Path,
        language: str = "english",
        quantize: bool = False,
        voice_source: str = "default",
        default_voice: str = "alba",
        custom_voice_name: str = "",
        volume_gain: float = 1.0,
    ) -> None:
        self.voice_path = str(voice_path)
        self.language = language
        self.quantize = quantize
        self.voice_source = voice_source
        self.default_voice = default_voice
        self.custom_voice_name = custom_voice_name
        self.volume_gain = _clamp_volume_gain(volume_gain)
        self._model = None
        self._voice_state = None
        self._lock = threading.Lock()
        self._cancel_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._status_queue: queue.Queue[str] = queue.Queue()

    @property
    def status_queue(self) -> queue.Queue[str]:
        return self._status_queue

    def speak_async(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        cancel_event = self._begin_new_stream()
        threading.Thread(target=self._speak, args=(text, cancel_event), daemon=True).start()

    def preload_async(self) -> None:
        threading.Thread(target=self._preload, daemon=True).start()

    def test_async(self) -> None:
        self.speak_async("This is a Pocket TTS test.")

    def close(self) -> None:
        self.stop()

    def stop(self) -> None:
        with self._cancel_lock:
            self._cancel_event.set()

    def _begin_new_stream(self) -> threading.Event:
        with self._cancel_lock:
            self._cancel_event.set()
            self._cancel_event = threading.Event()
            return self._cancel_event

    def _preload(self) -> None:
        with self._lock:
            try:
                self._load()
            except Exception as exc:
                self._status_queue.put(f"TTS preload error: {exc}")

    def _load(self) -> None:
        if self._model is not None and self._voice_state is not None:
            return
        self._status_queue.put("Loading Pocket TTS model...")
        try:
            pocket_tts = importlib.import_module("pocket_tts")
            tts_model = getattr(pocket_tts, "TTSModel")
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                "Pocket TTS failed to load through the in-process Python API. "
                "Use the uvx-server backend, especially from the bundled EXE."
            ) from exc

        try:
            self._model = tts_model.load_model(language=self.language, quantize=self.quantize)
        except OSError as exc:
            raise RuntimeError(
                "Pocket TTS/Torch DLL initialization failed in the in-process Python API. "
                "Use the uvx-server backend instead."
            ) from exc
        voice = self.default_voice if self.voice_source == "default" else self._custom_voice_path()
        self._status_queue.put(f"Loading voice: {voice}")
        self._voice_state = self._model.get_state_for_audio_prompt(voice)
        self._status_queue.put("Pocket TTS ready.")

    def _custom_voice_path(self) -> str:
        if not self.voice_path.strip():
            raise ValueError("Select a WAV or MP3 file, or change Voice Source to default.")
        return str(_prepared_audio_prompt_path(self.voice_path, self.language, self._status_queue))

    def _speak(self, text: str, cancel_event: threading.Event) -> None:
        with self._lock:
            try:
                self._load()
                if cancel_event.is_set():
                    self._status_queue.put("Stopped previous TTS stream.")
                    return
                assert self._model is not None
                assert self._voice_state is not None
                sample_rate = int(self._model.sample_rate)
                self._status_queue.put("Speaking OCR text...")
                with sd.OutputStream(samplerate=sample_rate, channels=1, dtype="float32") as stream:
                    for chunk in self._model.generate_audio_stream(self._voice_state, text):
                        if cancel_event.is_set():
                            self._status_queue.put("Stopped previous TTS stream.")
                            return
                        audio = chunk.detach().cpu().numpy()
                        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
                        if audio.size:
                            stream.write(_apply_volume_gain(audio, self.volume_gain))
                self._status_queue.put("Done.")
            except Exception as exc:
                self._status_queue.put(f"TTS error: {exc}")


class UvxPocketTTSServer:
    def __init__(
        self,
        voice_path: str | Path,
        language: str = "english",
        quantize: bool = False,
        host: str = "localhost",
        port: int = 8000,
        voice_source: str = "default",
        default_voice: str = "alba",
        custom_voice_name: str = "",
        volume_gain: float = 1.0,
    ) -> None:
        self.voice_path = str(voice_path)
        self.language = language
        self.quantize = quantize
        self.host = host
        self.port = port
        self.voice_source = voice_source
        self.default_voice = default_voice
        self.custom_voice_name = custom_voice_name
        self.volume_gain = _clamp_volume_gain(volume_gain)
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._speak_lock = threading.Lock()
        self._cancel_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._active_response: requests.Response | None = None
        self._server_output: collections.deque[str] = collections.deque(maxlen=80)
        self._status_queue: queue.Queue[str] = queue.Queue()

    @property
    def status_queue(self) -> queue.Queue[str]:
        return self._status_queue

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def preload_async(self) -> None:
        threading.Thread(target=self._ensure_server, daemon=True).start()

    def speak_async(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        cancel_event = self._begin_new_stream()
        threading.Thread(target=self._speak, args=(text, cancel_event), daemon=True).start()

    def test_async(self) -> None:
        self.speak_async("This is a Pocket TTS test.")

    def close(self) -> None:
        self.stop()
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def stop(self) -> None:
        with self._cancel_lock:
            self._cancel_event.set()
            if self._active_response is not None:
                self._active_response.close()

    def _begin_new_stream(self) -> threading.Event:
        with self._cancel_lock:
            self._cancel_event.set()
            if self._active_response is not None:
                self._active_response.close()
            self._cancel_event = threading.Event()
            return self._cancel_event

    def _is_healthy(self) -> bool:
        try:
            response = requests.get(urljoin(self.base_url, "health"), timeout=2)
            return response.ok
        except requests.RequestException:
            return False

    def _ensure_server(self) -> None:
        with self._lock:
            if self._is_healthy():
                self._status_queue.put("Pocket TTS server ready.")
                return
            if self._process is None or self._process.poll() is not None:
                uvx = _find_uvx()
                command = [
                    str(uvx),
                    "pocket-tts",
                    "serve",
                    "--host",
                    self.host,
                    "--port",
                    str(self.port),
                    "--language",
                    self.language,
                ]
                if self.quantize:
                    command.append("--quantize")
                self._server_output.clear()
                self._status_queue.put(f"Starting Pocket TTS server with {uvx}...")
                self._process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=_clean_subprocess_env(),
                    cwd=str(Path.home()),
                    creationflags=_subprocess_creationflags(),
                )
                threading.Thread(target=self._read_server_output, daemon=True).start()
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                if self._is_healthy():
                    self._status_queue.put("Pocket TTS server ready.")
                    return
                if self._process and self._process.poll() is not None:
                    output = self._server_output_tail()
                    detail = f"\n{output}" if output else " No server output was captured."
                    raise RuntimeError(f"Pocket TTS server exited with code {self._process.returncode}.{detail}")
                time.sleep(1)
            raise TimeoutError("Pocket TTS server did not become ready before timeout.")

    def _read_server_output(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                line = line.strip()
                if line:
                    self._server_output.append(line)
        except Exception as exc:
            self._server_output.append(f"Failed to read server output: {exc}")

    def _server_output_tail(self) -> str:
        if not self._server_output:
            return ""
        return "\n".join(list(self._server_output)[-12:])

    def _speak(self, text: str, cancel_event: threading.Event) -> None:
        with self._speak_lock:
            if cancel_event.is_set():
                self._status_queue.put("Stopped previous TTS stream.")
                return
            try:
                self._ensure_server()
                if cancel_event.is_set():
                    self._status_queue.put("Stopped previous TTS stream.")
                    return
                self._status_queue.put("Requesting Pocket TTS audio...")
                if self.voice_source == "default":
                    response = requests.post(
                        urljoin(self.base_url, "tts"),
                        data={"text": text, "voice_url": self.default_voice},
                        stream=True,
                        timeout=900,
                    )
                else:
                    voice_url = self._custom_voice_url()
                    response = requests.post(
                        urljoin(self.base_url, "tts"),
                        data={"text": text, "voice_url": voice_url},
                        stream=True,
                        timeout=900,
                    )
                with self._cancel_lock:
                    self._active_response = response
                response.raise_for_status()
                self._play_streaming_wav(response, cancel_event)
                if not cancel_event.is_set():
                    self._status_queue.put("Done.")
            except requests.RequestException as exc:
                if cancel_event.is_set():
                    self._status_queue.put("Stopped previous TTS stream.")
                else:
                    self._status_queue.put(f"TTS error: {exc}")
            except Exception as exc:
                self._status_queue.put(f"TTS error: {exc}")
            finally:
                with self._cancel_lock:
                    self._active_response = None

    def _custom_voice_path(self) -> str:
        if not self.voice_path.strip():
            raise ValueError("Select a WAV or MP3 file, or change Voice Source to default.")
        return self.voice_path

    def _custom_voice_url(self) -> str:
        voice_state = _cached_voice_state_path(
            self._custom_voice_path(),
            self.language,
            self._status_queue,
            self.custom_voice_name,
        )
        return _voice_state_server.url_for(voice_state)

    def _play_streaming_wav(self, response: requests.Response, cancel_event: threading.Event) -> None:
        buffer = bytearray()
        stream: sd.OutputStream | None = None
        sample_width = 0
        channels = 0
        try:
            for chunk in response.iter_content(chunk_size=16384):
                if cancel_event.is_set():
                    response.close()
                    self._status_queue.put("Stopped previous TTS stream.")
                    return
                if not chunk:
                    continue
                buffer.extend(chunk)
                if stream is None:
                    header_end = _find_wav_data_offset(buffer)
                    if header_end is None:
                        continue
                    channels, sample_rate, sample_width = _read_wav_format(buffer)
                    stream = sd.OutputStream(samplerate=sample_rate, channels=channels, dtype="float32")
                    stream.start()
                    del buffer[:header_end]
                    self._status_queue.put("Streaming Pocket TTS audio...")
                frame_size = sample_width * channels
                usable = len(buffer) - (len(buffer) % frame_size)
                if usable <= 0:
                    continue
                pcm = bytes(buffer[:usable])
                del buffer[:usable]
                audio = _pcm_to_float32(pcm, sample_width, channels)
                if audio.size:
                    stream.write(_apply_volume_gain(audio, self.volume_gain))
        finally:
            if stream is not None:
                stream.stop()
                stream.close()


class _QuietStaticFileHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *args: object) -> None:
        return


class _VoiceStateServer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def url_for(self, path: Path) -> str:
        with self._lock:
            VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if self._server is None:
                handler = functools.partial(_QuietStaticFileHandler, directory=str(VOICE_CACHE_DIR))
                self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
                self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
                self._thread.start()
            port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}/{quote(path.name)}"


_voice_state_server = _VoiceStateServer()


def _cached_voice_state_path(
    source_path: str,
    language: str,
    status_queue: queue.Queue[str],
    voice_name: str = "",
) -> Path:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Voice file not found: {source}")
    VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stat = source.stat()
    digest = hashlib.sha256(
        f"{source.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{language}".encode("utf-8")
    ).hexdigest()[:24]
    prefix = safe_voice_slug(voice_name) if voice_name.strip() else source.stem
    target = VOICE_CACHE_DIR / f"{safe_voice_slug(prefix)}-{digest}.safetensors"
    if source.suffix.casefold() == ".safetensors":
        if not target.exists():
            shutil.copy2(source, target)
        status_queue.put("Using cached custom voice state.")
        return target
    if target.exists():
        status_queue.put("Using cached custom voice state.")
        return target

    prompt_source = _prepared_audio_prompt_path(source, language, status_queue, digest)
    status_queue.put("Exporting custom voice cache; first run can take a while.")
    command = [
        str(_find_uvx()),
        "pocket-tts",
        "export-voice",
        str(prompt_source),
        str(target),
        "--language",
        language,
        "--quiet",
    ]
    subprocess.run(command, check=True, env=_clean_subprocess_env(), creationflags=_subprocess_creationflags())
    status_queue.put("Custom voice cache ready.")
    return target


def _prepared_audio_prompt_path(
    source_path: str | Path,
    language: str,
    status_queue: queue.Queue[str],
    digest: str | None = None,
) -> Path:
    source = Path(source_path)
    if source.suffix.casefold() != ".mp3":
        return source
    VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if digest is None:
        stat = source.stat()
        digest = hashlib.sha256(
            f"{source.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{language}".encode("utf-8")
        ).hexdigest()[:24]
    target = VOICE_CACHE_DIR / f"{safe_voice_slug(source.stem)}-{digest}.wav"
    if target.exists():
        status_queue.put("Using cached WAV conversion for MP3 voice.")
        return target
    status_queue.put("Converting MP3 voice reference to WAV...")
    _convert_mp3_to_wav(source, target)
    status_queue.put("MP3 voice conversion ready.")
    return target


def _convert_mp3_to_wav(source: Path, target: Path) -> None:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError("MP3 custom voices require imageio-ffmpeg. Reinstall Seshat TTS dependencies.") from exc

    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "24000",
        "-sample_fmt",
        "s16",
        str(target),
    ]
    subprocess.run(command, check=True, env=_clean_subprocess_env(), creationflags=_subprocess_creationflags())


def _find_wav_data_offset(data: bytearray) -> int | None:
    marker = data.find(b"data")
    if marker < 0 or len(data) < marker + 8:
        return None
    return marker + 8


def _read_wav_format(data: bytearray) -> tuple[int, int, int]:
    if len(data) < 36 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Response is not a WAV stream.")
    fmt = data.find(b"fmt ")
    if fmt < 0 or len(data) < fmt + 24:
        raise ValueError("WAV stream is missing fmt chunk.")
    channels = int.from_bytes(data[fmt + 10 : fmt + 12], "little")
    sample_rate = int.from_bytes(data[fmt + 12 : fmt + 16], "little")
    bits_per_sample = int.from_bytes(data[fmt + 22 : fmt + 24], "little")
    return channels, sample_rate, bits_per_sample // 8


def _pcm_to_float32(pcm: bytes, sample_width: int, channels: int) -> np.ndarray:
    if sample_width == 2:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(pcm, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    if channels > 1:
        return audio.reshape(-1, channels)
    return audio.reshape(-1, 1)


def _clamp_volume_gain(value: float) -> float:
    return max(0.0, min(float(value), 3.0))


def _apply_volume_gain(audio: np.ndarray, volume_gain: float) -> np.ndarray:
    gain = _clamp_volume_gain(volume_gain)
    if gain == 1.0:
        return audio
    return np.clip(audio * gain, -1.0, 1.0).astype(np.float32, copy=False)


def _find_uvx() -> Path:
    bundled = resource_path("tools/uvx.exe")
    if bundled.exists():
        return bundled
    found = shutil.which("uvx")
    if found:
        return Path(found)
    candidates = [
        Path.home() / ".local" / "bin" / "uvx.exe",
        Path.home() / ".cargo" / "bin" / "uvx.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("uvx.exe was not found on PATH. Install uv or add uvx.exe to PATH.")


def _clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("_PYI") or key.startswith("PYINSTALLER"):
            env.pop(key, None)
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)

    user_bin = Path.home() / ".local" / "bin"
    if user_bin.exists():
        env["PATH"] = str(user_bin) + os.pathsep + env.get("PATH", "")
    return env


def _subprocess_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
