# Architecture

Seshat TTS is a Windows desktop utility that converts selected on-screen text into streamed speech.

## Runtime Flow

1. User selects a monitor or window.
2. User selects a screen region.
3. Hotkey triggers capture.
4. Tesseract OCR extracts text from the selected region, unless LLM image extraction is enabled.
5. Optional local OpenAI-compatible LLM cleans the OCR text, or a vision-capable local LLM extracts text directly from the captured region image.
6. Pocket TTS streams speech.
7. New hotkey captures stop any active stream and start a fresh one.
8. Stop hotkey cancels active playback without starting another capture.

## Key Modules

- `src/seshat_tts/app.py`: Tk GUI, settings flow, hotkey orchestration.
- `src/seshat_tts/capture.py`: monitor/window capture.
- `src/seshat_tts/region_picker.py`: snipping-tool-style region selection.
- `src/seshat_tts/ocr.py`: image preprocessing and Tesseract OCR.
- `src/seshat_tts/tts.py`: Pocket TTS API/server playback.
- `src/seshat_tts/llm.py`: OpenAI-compatible local LLM cleanup and vision-based image text extraction.
- `src/seshat_tts/config.py`: persisted config loading and migration.
- `src/seshat_tts/voices.py`: named custom voice profiles.

## Packaging

`scripts/build_exe.ps1` builds a portable PyInstaller executable using `seshat-tts-portable.spec`.

The packaged EXE includes first-party resources, project license, third-party notices, bundled OCR files when Tesseract is installed on the build machine, and `uvx.exe` when found.

Pocket TTS runs through `uvx-server` in bundled builds to avoid freezing Torch and its native dependencies into the app.
