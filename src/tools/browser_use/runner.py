"""Run Browser Use agents through OpenRouter."""

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


def _load_dependencies() -> tuple[Any, Any]:
    """Delay optional imports so normal graph startup needs no browser stack."""
    try:
        from browser_use import Agent, ChatOpenAI
    except ImportError as exc:
        raise BrowserUseConfigurationError(
            "Browser Use is not installed. Run `pip install -r requirements.txt` "
            "and then install its browser runtime with `browser-use install`."
        ) from exc
    return Agent, ChatOpenAI


async def _run_with_model(
    task: str,
    *,
    config: BrowserUseConfig,
) -> str:
    """Create a Browser Use agent backed by OpenRouter's OpenAI-compatible API."""
    Agent, ChatOpenAI = _load_dependencies()
    llm = ChatOpenAI(
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
        temperature=0,
        frequency_penalty=None,
        # OpenRouter Gemma does not accept response_format=json_schema. Browser Use
        # appends its action schema to the system prompt and validates the
        # returned JSON locally instead.
        add_schema_to_system_prompt=True,
        dont_force_structured_output=True,
    )
    agent = Agent(
        task=task,
        llm=llm,
        # google/gemma-4-31b-it:free is text-only, so Browser Use relies on its DOM
        # and accessibility representation instead of screenshots.
        use_vision=False,
        max_failures=config.max_failures,
        # The OpenRouter free tier for this Gemma model permits limited TPM. The
        # Browser Use default exposes up to 40k characters of clickable DOM
        # state, which makes even the first form step exceed that quota.
        # DemoQA's relevant fields appear near the top of the accessibility
        # tree, so a compact slice is sufficient and keeps each agent turn
        # within the provider limit.
        max_clickable_elements_length=4_000,
        max_history_items=6,
        # Shrink Browser Use's output schema as well as the page state. Gemma
        # does not need a multi-action plan to complete a straightforward
        # form, and OpenRouter counts the schema against its TPM budget.
        max_actions_per_step=1,
        use_thinking=False,
        enable_planning=False,
    )
    history = await agent.run(max_steps=config.max_steps)
    final_result = history.final_result()
    return str(final_result) if final_result is not None else "Browser task completed without a final result."


async def run_browser_task(
    task: str,
    config: BrowserUseConfig | None = None,
) -> BrowserTaskResult:
    """Run a Browser Use task with OpenRouter's Gemma model."""
    config = config or BrowserUseConfig.from_env()
    if not config.api_key:
        raise BrowserUseConfigurationError(
            "OPENROUTER_API_KEY is required for Browser Use tasks."
        )
    result = await _run_with_model(task, config=config)
    return BrowserTaskResult(
        result=result,
        model=config.model,
        use_vision=False,
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
