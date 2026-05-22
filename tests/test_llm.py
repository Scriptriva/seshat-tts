from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from seshat_tts.llm import process_image_with_llm, process_text_with_llm


@dataclass
class _Message:
    content: str


@dataclass
class _Choice:
    message: _Message


@dataclass
class _Response:
    choices: list[_Choice]


class _Completions:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object) -> _Response:
        self.kwargs = kwargs
        return _Response([_Choice(_Message("Cleaned text."))])


class _Client:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _Completions()})()


def test_llm_disabled_returns_original_text() -> None:
    assert (
        process_text_with_llm(
            " OCR text ",
            enabled=False,
            base_url="http://127.0.0.1:8000/v1",
            api_key="local",
            model="unsloth",
            system_prompt="clean",
        )
        == "OCR text"
    )


def test_llm_enabled_uses_openai_compatible_chat_client() -> None:
    client = _Client()

    result = process_text_with_llm(
        "OCR text",
        enabled=True,
        base_url="http://127.0.0.1:8000/v1",
        api_key="local",
        model="unsloth-model",
        system_prompt="clean",
        timeout=1,
        max_tokens=32,
        client=client,
    )

    assert result == "Cleaned text."
    assert client.chat.completions.kwargs is not None
    assert client.chat.completions.kwargs["model"] == "unsloth-model"
    assert client.chat.completions.kwargs["temperature"] == 0
    assert client.chat.completions.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False},
        "enable_thinking": False,
        "reasoning_effort": "none",
    }


def test_llm_can_send_without_disable_thinking_metadata() -> None:
    client = _Client()

    process_text_with_llm(
        "OCR text",
        enabled=True,
        base_url="http://127.0.0.1:8000/v1",
        api_key="local",
        model="unsloth-model",
        system_prompt="clean",
        disable_thinking=False,
        client=client,
    )

    assert client.chat.completions.kwargs is not None
    assert "extra_body" not in client.chat.completions.kwargs


def test_llm_can_extract_text_from_image_region() -> None:
    client = _Client()
    image = Image.new("RGB", (16, 8), "black")

    result = process_image_with_llm(
        image,
        base_url="http://127.0.0.1:8000/v1",
        api_key="local",
        model="vision-model",
        timeout=1,
        max_tokens=64,
        client=client,
    )

    assert result == "Cleaned text."
    assert client.chat.completions.kwargs is not None
    assert client.chat.completions.kwargs["model"] == "vision-model"
    messages = client.chat.completions.kwargs["messages"]
    user_content = messages[1]["content"]
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")
