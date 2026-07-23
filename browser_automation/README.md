# Browser Use + OpenRouter

This project runs Browser Use with NVIDIA Nemotron 3 Nano Omni through OpenRouter.

## One-time setup

```bash
cp .env.example .env
# Edit .env and replace the placeholder with your OpenRouter API key.
uv sync --python 3.12
uv run browser-use install
```

## Run

```bash
uv run python main.py
```

The configured model is `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`.

Change the `task` in `main.py` for the browser workflow you need. The included task is deliberately read-only.
