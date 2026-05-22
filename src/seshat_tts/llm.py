from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image


DEFAULT_API_KEY_PATH = Path.home() / ".seshat-tts" / "llm_api_key.txt"
IMAGE_EXTRACTION_SYSTEM_PROMPT = (
    "Extract only the visible readable text from the supplied image for text-to-speech. "
    "Preserve the original wording and sentence order. Do not describe the image, "
    "do not add commentary, and do not include UI labels unless they are part of the text to read."
)
IMAGE_EXTRACTION_USER_PROMPT = "Read the text in this selected screen region and return only that text."


class _ChatCompletions(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _Chat(Protocol):
    completions: _ChatCompletions


class _OpenAIClient(Protocol):
    chat: _Chat


def load_api_key_file(path: Path = DEFAULT_API_KEY_PATH) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def process_text_with_llm(
    text: str,
    *,
    enabled: bool,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    timeout: float = 5.0,
    max_tokens: int = 256,
    disable_thinking: bool = True,
    client: _OpenAIClient | None = None,
) -> str:
    text = text.strip()
    if not enabled or not text:
        return text

    if client is None:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key.strip() or "local",
            base_url=base_url.strip(),
            timeout=max(0.1, float(timeout)),
        )

    request: dict[str, object] = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": text},
        ],
        "temperature": 0,
        "max_tokens": max(1, int(max_tokens)),
        "stream": False,
    }
    if disable_thinking:
        request["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": False},
            "enable_thinking": False,
            "reasoning_effort": "none",
        }

    response = client.chat.completions.create(**request)
    content = response.choices[0].message.content
    return str(content or "").strip() or text


def process_image_with_llm(
    image: Image.Image,
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 5.0,
    max_tokens: int = 256,
    disable_thinking: bool = True,
    client: _OpenAIClient | None = None,
) -> str:
    if client is None:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key.strip() or "local",
            base_url=base_url.strip(),
            timeout=max(0.1, float(timeout)),
        )

    request: dict[str, object] = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": IMAGE_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": IMAGE_EXTRACTION_USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{_image_to_base64_png(image)}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": max(1, int(max_tokens)),
        "stream": False,
    }
    if disable_thinking:
        request["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": False},
            "enable_thinking": False,
            "reasoning_effort": "none",
        }

    response = client.chat.completions.create(**request)
    content = response.choices[0].message.content
    return str(content or "").strip()


def _image_to_base64_png(image: Image.Image) -> str:
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")
