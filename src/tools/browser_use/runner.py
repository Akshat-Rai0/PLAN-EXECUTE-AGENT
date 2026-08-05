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
    """
    Run a Browser Use task through OpenRouter free model adapter.

    WHEN TO USE:
    - When you need to interact with rendered websites (not just scrape HTML)
    - For form filling and submission on web pages
    - When visual page understanding is required (identifying elements by sight)
    - For multi-step interactions requiring page state persistence
    - When JavaScript-rendered content needs to be accessed
    - For tasks that require human-like browsing behavior

    WHEN NOT TO USE:
    - For simple information retrieval (use tavily_search instead)
    - When static HTML scraping would suffice (use search/code_executor)
    - For API calls or data fetching (use code_executor with requests library)
    - When the task doesn't require visual element identification
    - For high-volume automated scraping (browser is resource-intensive)

    EXAMPLES:
    - "Navigate to Google Travel flights and search for SFO to JFK flights"
    - "Go to example.com and extract the main heading text"
    - "Fill out a contact form with name, email, and message"
    - "Navigate to weather.com and find current temperature for London"
    - "Go to GitHub and find trending repositories with their languages"
    - "Login to a dashboard and navigate to the settings page"

    CAPABILITIES:
    - Vision-enabled page understanding (identifies elements visually)
    - Form filling and submission
    - Multi-step navigation with session persistence
    - Dynamic content interaction (JavaScript-heavy sites)
    - Element identification using visual cues and DOM structure
    - Screenshot generation for debugging

    TECHNICAL DETAILS:
    - Uses OpenRouter's Gemma model with structured outputs
    - Vision capabilities enabled for rendered page analysis
    - Session persistence across steps within a single task
    - Configurable step limits and failure tolerance
    - HIGH-risk classification (requires approval before execution)

    Args:
        task: Natural language description of the browser task to perform
        config: Optional BrowserUseConfig (uses environment defaults if not provided)

    Returns:
        BrowserTaskResult containing the task result, model used, vision status, and provider

    Raises:
        BrowserUseConfigurationError: If OPENROUTER_API_KEY is not configured
    """
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
