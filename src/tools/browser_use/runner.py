"""Run Browser Use agents through OpenRouter using FreeOpenRouterChat adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .config import BrowserUseConfig


class BrowserUseConfigurationError(RuntimeError):
    """Raised when the Browser Use integration cannot be configured."""


@dataclass(frozen=True)
class BrowserTaskResult:
    """A serializable summary of one Browser Use run."""

    result: str
    model: str
    use_vision: bool
    provider: str


def _load_agent() -> Any:
    """Delay optional import so normal graph startup needs no browser stack."""
    try:
        from browser_use import Agent
    except ImportError as exc:
        raise BrowserUseConfigurationError(
            "Browser Use is not installed. Run `pip install -r requirements.txt` "
            "and then install its browser runtime with `browser-use install`."
        ) from exc
    return Agent


async def _run_with_model(
    task: str,
    *,
    config: BrowserUseConfig,
) -> str:
    """Create a Browser Use agent backed by the FreeOpenRouterChat adapter."""
    from .free_openrouter import FreeOpenRouterChat

    Agent = _load_agent()

    llm = FreeOpenRouterChat(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0,
    )

    agent = Agent(
        task=task,
        llm=llm,
        use_vision=True,
        max_failures=config.max_failures,
        max_clickable_elements_length=config.max_clickable_elements_length,
        max_history_items=8,
        max_actions_per_step=3,
        use_thinking=False,
        enable_planning=False,
        generate_gif=True,
    )
    history = await agent.run(max_steps=config.max_steps)
    final_result = history.final_result()
    return str(final_result) if final_result is not None else "Browser task completed without a final result."


async def run_browser_task(
    task: str,
    config: BrowserUseConfig | None = None,
) -> BrowserTaskResult:
    """Run a Browser Use task through OpenRouter free model adapter."""
    config = config or BrowserUseConfig.from_env()
    if not config.api_key:
        raise BrowserUseConfigurationError(
            "OPENROUTER_API_KEY is required for Browser Use tasks."
        )
    result = await _run_with_model(task, config=config)
    return BrowserTaskResult(
        result=result,
        model=config.model,
        use_vision=True,
        provider="openrouter",
    )


def run_browser_task_sync(
    task: str,
    config: BrowserUseConfig | None = None,
) -> BrowserTaskResult:
    """Synchronous adapter used by the synchronous LangGraph node."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_browser_task(task, config))
    raise RuntimeError(
        "run_browser_task_sync cannot be called from an active event loop; "
        "await run_browser_task(...) instead."
    )
