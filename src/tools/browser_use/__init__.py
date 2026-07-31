"""Browser Use integration backed by OpenRouter models."""

from .config import BrowserUseConfig
from .runner import BrowserTaskResult, run_browser_task, run_browser_task_sync

__all__ = [
    "BrowserTaskResult",
    "BrowserUseConfig",
    "run_browser_task",
    "run_browser_task_sync",
]
