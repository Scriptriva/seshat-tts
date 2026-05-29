# Contributing

Thank you for helping improve Seshat TTS. This project is maintained by Scriptriva and welcomes focused community contributions.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
$env:PYTHONPATH='src'
python -m pytest -q
```

## Contribution Areas

- OCR accuracy and preprocessing.
- Window capture reliability.
- TTS stream cancellation and playback.
- Local OpenAI-compatible LLM cleanup.
- Packaging and documentation.
- Accessibility and usability.

## Pull Request Expectations

- Keep changes scoped and explain user-visible behavior.
- Add or update tests for behavior changes.
- Do not commit secrets, voice samples, generated voice caches, build outputs, or local config files.
- Preserve third-party notices and license files.
- Follow existing code style and avoid unrelated refactors.
- Run `python -m pytest -q` before opening a pull request.

## Licensing

By contributing, you agree that your contribution may be used under the MIT license for this project. You also confirm that you have the right to submit the contribution.

## Security

Do not open public issues for vulnerabilities. Follow [SECURITY.md](SECURITY.md).
