"""
Process-level registry of live BrowserExecutor sessions, keyed by thread_id.

Why this exists: BrowserExecutor wraps a real Playwright browser process,
which is not serializable and cannot live inside LangGraph's checkpointed
State (that gets persisted to SQLite between steps). Without some place to
park the live object between node invocations, every browser_node call was
constructing a brand-new BrowserExecutor and tearing it down again at the
end of the *step* -- so each browser step started over from about:blank,
losing whatever navigation the previous step had already done within the
same goal run. This directly contradicted the documented design ("session
persists across steps within one goal run").

This module is intentionally simple: a module-level dict living for the
lifetime of the Python process. It is NOT multi-process safe and is NOT
meant to survive process restarts -- that's fine, because a goal run's
thread_id is only ever driven from a single process in the current CLI
flow. If this ever needs to work across worker processes, this should be
replaced with something like a keyed subprocess pool instead.
"""

from typing import Dict

from src.executor.browser_executor import BrowserExecutor

_sessions: Dict[str, BrowserExecutor] = {}


def get_or_create_session(thread_id: str, **executor_kwargs) -> BrowserExecutor:
    """
    Return the existing BrowserExecutor for this thread_id if one is already
    alive, otherwise construct a new one and register it.
    """
    existing = _sessions.get(thread_id)
    if existing is not None:
        return existing

    executor = BrowserExecutor(**executor_kwargs)
    _sessions[thread_id] = executor
    return executor


def close_session(thread_id: str) -> None:
    """Close and forget the browser session for this thread_id, if any."""
    executor = _sessions.pop(thread_id, None)
    if executor is not None:
        try:
            executor.close()
        except Exception:
            pass


def close_all_sessions() -> None:
    """Close every live session. Useful as a last-resort cleanup on process exit."""
    for thread_id in list(_sessions.keys()):
        close_session(thread_id)


def has_session(thread_id: str) -> bool:
    return thread_id in _sessions
