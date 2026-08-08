"""
Lightweight observer hooks for graph nodes.

Uses contextvars so nodes can emit visualization events without
changing orchestration logic — read-only observer over execution.
"""

from __future__ import annotations

import contextvars
import contextvars as cv
from typing import Callable, Optional

from .models import ArmName, RunStepEvent

_emit_callback: contextvars.ContextVar[Optional[Callable[[RunStepEvent], None]]] = (
    contextvars.ContextVar("run_event_emitter", default=None)
)
_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("viz_run_id", default="")
_run_arm: contextvars.ContextVar[ArmName] = contextvars.ContextVar(
    "viz_run_arm", default="plan_execute_synthesis"
)


def set_emitter(callback: Optional[Callable[[RunStepEvent], None]]) -> contextvars.Token:
    return _emit_callback.set(callback)


def set_run_context(run_id: str, arm: ArmName) -> tuple[contextvars.Token, contextvars.Token]:
    return _run_id.set(run_id), _run_arm.set(arm)


def reset_emitter(token: contextvars.Token) -> None:
    _emit_callback.reset(token)


def reset_run_context(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    _run_id.reset(tokens[0])
    _run_arm.reset(tokens[1])


def emit_event(event: RunStepEvent) -> None:
    callback = _emit_callback.get()
    if callback is not None:
        if not event.run_id:
            event.run_id = _run_id.get()
        if not event.arm:
            event.arm = _run_arm.get()
        callback(event)


def current_run_id() -> str:
    return _run_id.get()


def current_arm() -> ArmName:
    return _run_arm.get()
