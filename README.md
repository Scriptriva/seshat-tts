# Seshat TTS

![Scriptriva Inc.](resources/banner.jpg)

<p align="center">
  <img src="resources/logo.png" alt="Scriptriva Inc. logo" width="160">
</p>

[![Python 3.10-3.14](https://img.shields.io/badge/python-3.10--3.14-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![Windows](https://img.shields.io/badge/platform-Windows-0078d4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![License: SPSL 1.0](https://img.shields.io/badge/license-SPSL%201.0-green.svg)](LICENSE)
[![Pocket TTS](https://img.shields.io/badge/voice-Kyutai%20Pocket%20TTS-111827)](https://github.com/kyutai-labs/pocket-tts)
[![Tesseract OCR](https://img.shields.io/badge/OCR-Tesseract-4b5563)](https://github.com/tesseract-ocr/tesseract)

Seshat TTS is a Windows GUI utility for realtime audio streaming for games, or apps. Pick a monitor or window, drag one capture region over the text, press one hotkey, and the selected text is extracted with Tesseract OCR or a local vision LLM, then streamed through Kyutai Pocket TTS.

Maintained by Scriptriva Inc.

For support inquiries email: support@scriptriva.com
<p align="center">
   <img src="resources/anime_meme.gif" alt="Anime girl studying">
<p>


## What It Does

- Captures one selected screen region from a monitor or a chosen window.
- Runs Tesseract OCR on that exact region, or sends the region image directly to a local vision-capable LLM for text extraction.
- Streams the extracted text through Pocket TTS in realtime.
- Lets you use a built-in Pocket TTS voice for speed or upload a custom WAV/MP3 reference voice.
- Optionally routes OCR text through a local OpenAI-compatible LLM endpoint before speech.
- Includes a 0-300% playback volume slider for quiet voices or noisy games.
- Stops any active audio stream when a new read starts, so repeated hotkey presses do not overlap.
- Caches custom voice state as `.safetensors` for faster repeat custom-voice reads when using the `uvx-server` backend.

<p align="center">
   <img src="resources/anime_yapping.gif" alt="Fast yapping mode">
<p>

## Requirements

- Windows 10/11.
- Python 3.10 through 3.14 when running from source or building.
- Tesseract OCR for Windows when running from source or building a portable EXE with bundled OCR.
- `uvx` when running from source, or when building a portable EXE with bundled uvx.
- A working audio output device.

Install Tesseract:

```powershell
winget install UB-Mannheim.TesseractOCR
```

Install `uvx`:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Install Seshat TTS for development or for the fast launcher:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[test]
```

## Build Before Use

For a single-file portable EXE, build with:

```powershell
.\scripts\build_exe.ps1
```

Portable output:

```powershell
.\dist\seshat-tts.exe
```

That EXE bundles the Seshat GUI/runtime files, app resources, `uvx.exe` if it is available on the build machine, and Tesseract OCR files if Tesseract is installed at `C:\Program Files\Tesseract-OCR`. You can override the OCR bundle source before building:

```powershell
$env:SESHAT_TESSERACT_DIR='D:\Tools\Tesseract-OCR'
.\scripts\build_exe.ps1
```

For the old one-folder PyInstaller build:

```powershell
.\scripts\build_exe.ps1 -OneDir
```

One-folder output:

```text
dist\seshat-tts\seshat-tts.exe
```

The portable EXE still uses Pocket TTS through `uvx-server`. It does not freeze Torch/Pocket TTS inside the EXE because that path has been unreliable on Windows and can trigger native DLL initialization failures. First Pocket TTS use can still download/cache the Pocket TTS tool and model data under the user's normal cache directories, but no separate Python, Tesseract, or uvx install should be needed when those files were bundled during build.

For a tiny development launcher, build:

```powershell
.\scripts\build_launcher_exe.ps1
```

Launcher output:

```text
dist\launcher\seshat-tts.exe
```

This launcher is intentionally small and quick to build. It uses the `.venv` in this project when present, so keep the virtual environment and installed dependencies beside the launcher.

## Run From Source

```powershell
seshat-tts
```

For the fast launcher EXE, run:

```powershell
.\dist\launcher\seshat-tts.exe
```

The launcher expects dependencies in `.venv` or your active Python environment. It does not bundle Python, Torch, Pocket TTS, or Tesseract.

## First-Time Setup

1. Open Seshat TTS.
2. Choose `monitor` or `window` capture mode.
3. Select the monitor or window to watch.
4. Click `Select Region`, then drag over the exact text area to read.
5. Click inside `Read Hotkey` and press the key combo you want. The default is `ctrl+alt+n`.
6. Click inside `Region Hotkey` and press the key combo you want. The default is `ctrl+alt+r`.
7. Click inside `Stop Hotkey` and press the key combo you want. The default is `ctrl+alt+s`.
8. Set `Tesseract` if it was not detected automatically.
9. Choose a voice:
   - `default` is fastest and uses a built-in Pocket TTS voice.
   - `custom-wav` lets you choose a named WAV, MP3, or cached `.safetensors` reference voice.
10. Adjust `Volume` if the generated voice is too quiet. `100%` is neutral; values above that boost and clip safely.
11. Enable `Local LLM` if you want OCR text cleaned by a local OpenAI-compatible server before TTS.
12. Enable `Use local LLM vision instead of Tesseract OCR` only when your local model endpoint supports image input and you want the LLM to read the selected region directly.
13. Click `Preload TTS` once before playing if you want the first read to be less delayed.
14. Press the read hotkey whenever the selected text should be spoken, or the stop hotkey whenever playback should stop.

Use borderless/windowed mode for games if exclusive fullscreen capture returns stale or blank frames.

## Local LLM

The `Local LLM` panel can use an OpenAI-compatible endpoint in two ways:

- `Route OCR through local OpenAI-compatible LLM` keeps Tesseract as the text extractor, then asks the local model to clean the parsed text before TTS.
- `Use local LLM vision instead of Tesseract OCR` skips Tesseract and sends the selected region image to the local model as a PNG data URL. This requires a vision-capable OpenAI-compatible model endpoint.

Typical values:

```text
Base URL: http://127.0.0.1:8000/v1
API Key: local key or token
Model: the model name exposed by your local server
```

`Load api_key.txt` fills the API key field from a repo-local `api_key.txt` file if present. Treat that file as a secret and do not commit it. Lower timeout and max token values reduce latency; no network or LLM path can be truly zero-latency, but a local endpoint keeps this as short as the model server allows.

`Disable thinking` is enabled by default. It sends common OpenAI-compatible metadata for local reasoning models, including `chat_template_kwargs.enable_thinking=false`, so models that support that switch skip reasoning output and return faster.

## Voice Modes

`default` voice mode is the fastest. Pick a built-in voice such as `alba`, `marius`, `anna`, `vera`, or `george`.

`custom-wav` mode accepts `.wav`, `.mp3`, and cached `.safetensors` voice files. MP3 references are converted once into cached WAV files before Pocket TTS processes them. Use `Manage` beside `Custom Voice` to name voices, save them, and select them from the dropdown.

The first custom-voice run can be slow because Pocket TTS must convert the reference audio into a voice state. Seshat TTS caches that state under:

```text
%USERPROFILE%\.seshat-tts\voices
```

After that cache exists, the `uvx-server` backend sends a reusable local `voice_url` instead of uploading and reprocessing the same audio every time. Named custom voices are stored in:

```text
%USERPROFILE%\.seshat-tts\voice_profiles.json
```

Pocket TTS voice cloning may require Hugging Face access:

1. Request access on [Kyutai's Pocket TTS Hugging Face page](https://huggingface.co/kyutai/pocket-tts).
2. Create a token at [Hugging Face tokens](https://huggingface.co/settings/tokens).
3. Login for `uvx`:

```powershell
uvx hf auth login --force
```

## Build Commands

Fast launcher build, usually under a minute:

```powershell
.\scripts\build_launcher_exe.ps1
```

Output:

```text
dist\launcher\seshat-tts.exe
```

Full dependency-bundled PyInstaller build:

```powershell
.\scripts\build_exe.ps1
```

Output:

```text
dist\seshat-tts.exe
```

Use the fast launcher during development and for local use. Use the portable build when you need to move the app to a machine where Python, Tesseract, and uvx are not installed.

The `python-api` backend is only shown when running from source or the fast launcher. The bundled PyInstaller EXE only exposes `uvx-server`.

## License and Reuse

Seshat TTS is released under the [Scriptriva Public Source License 1.0](LICENSE).

Copyright (c) 2026 Scriptriva Inc.

Commercial use is allowed under the license terms. The license preserves attribution, third-party notices, Scriptriva branding rights, safety restrictions, and restrictions on reusing the licensed work to create or distribute a same-functionality product.

Useful reuse boundaries:

- `src/seshat_tts/capture.py`: monitor/window capture helpers.
- `src/seshat_tts/ocr.py`: OCR preprocessing and text extraction.
- `src/seshat_tts/tts.py`: Pocket TTS server/API playback adapters and stream cancellation.
- `src/seshat_tts/llm.py`: OpenAI-compatible local LLM cleanup step.
- `src/seshat_tts/config.py`: persisted GUI/runtime configuration.
- `src/seshat_tts/region_picker.py`: snipping-tool-style region selection.

Security and privacy considerations for reuse:

- Treat OCR text, API keys, custom voice files, and generated voice caches as user data.
- Do not commit `api_key.txt`, voice samples, `.safetensors` voice caches, or local config files.
- Custom voice cloning should be used only with audio you have permission to use.
- The portable EXE may bundle third-party binaries; keep their notices and license terms intact.



## Third-Party Notices

Seshat TTS uses and/or interfaces with these third-party projects. Each project remains under its own license:

| Component | Purpose | License | Notes |
| --- | --- | --- | --- |
| [Kyutai Pocket TTS](https://github.com/kyutai-labs/pocket-tts) | Local text-to-speech generation and voice cloning | MIT | The Pocket TTS GitHub repository identifies the project as MIT licensed. Model/voice assets may have separate terms; review the linked Hugging Face pages before redistribution. |
| [Tesseract OCR](https://tesseractocr.org/) | OCR engine used to extract text from selected screen regions | Apache License 2.0 | Tesseract is not MIT licensed. Its project site identifies it as Apache 2.0 licensed. |
| [pytesseract](https://github.com/madmaze/pytesseract) | Python wrapper for Tesseract | Apache License 2.0 | Used to invoke the Tesseract executable from Python. |
| [PyInstaller](https://pyinstaller.org/) | Windows executable packaging | GPLv2-or-later with bootloader exception | Used only for building packaged executables. |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | OpenAI-compatible local LLM client | Apache License 2.0 | Used for optional local LLM cleanup through OpenAI-compatible endpoints. |

Packaged builds include [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), including a link to the [Pocket TTS MIT license](https://github.com/kyutai-labs/pocket-tts/blob/main/LICENSE).

## Tests

```powershell
$env:PYTHONPATH='src'
python -m pytest -q
```
