"""Configuration for Browser Use with OpenRouter's Gemini Flash model."""


from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


# Browser Use is also usable independently of the LangGraph CLI, whose LLM
# module normally loads this file. Load it here so direct browser tasks see
# OPENROUTER_API_KEY and the Browser Use settings as well.
load_dotenv()


# google/gemma-4-26b-a4b-it:free natively supports structured outputs (response_format) on OpenRouter
BROWSER_MODEL = "google/gemma-4-26b-a4b-it:free"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer environment variable, falling back safely."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class BrowserUseConfig:
    """Runtime options intentionally limited to safe, portable settings."""

    api_key: str | None
    model: str = BROWSER_MODEL
    base_url: str = OPENROUTER_BASE_URL
    max_steps: int = 25
    max_failures: int = 3

    @classmethod
    def from_env(cls) -> "BrowserUseConfig":
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv("BROWSER_USE_MODEL", BROWSER_MODEL),
            base_url=os.getenv("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
            max_steps=_positive_int("BROWSER_USE_MAX_STEPS", 25),
            max_failures=_positive_int("BROWSER_USE_MAX_FAILURES", 3),
        )
