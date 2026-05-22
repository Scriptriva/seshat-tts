# Security Policy

## Supported Versions

The `main` branch is the only supported development line until formal releases begin.

## Reporting a Vulnerability

Email support@scriptriva.com with:

- A concise description of the issue.
- Steps to reproduce.
- Affected version or commit.
- Impact and likely abuse path.
- Any proof-of-concept files or screenshots that are safe to share.

Please do not disclose vulnerabilities publicly until maintainers have had time to investigate and coordinate a fix.

## Sensitive Data

Do not commit:

- `api_key.txt`
- Hugging Face or OpenAI-compatible API tokens
- custom voice samples
- cached `.safetensors` voice states
- generated executable artifacts
- local config files

## Security-Relevant Areas

- Screen/window capture.
- OCR text handling.
- Local LLM endpoint configuration.
- Custom voice file handling.
- TTS server startup and subprocess execution.
- Packaged binary contents.
