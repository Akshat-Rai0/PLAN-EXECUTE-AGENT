from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from .models import RunStepEvent, StepPayload, utc_now_iso


class RunEventBus:
    """Pub/sub for live run step events over WebSocket."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[RunStepEvent | None]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, run_id: str) -> AsyncIterator[RunStepEvent]:
        queue: asyncio.Queue[RunStepEvent | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers[run_id].append(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            async with self._lock:
                subs = self._subscribers.get(run_id, [])
                if queue in subs:
                    subs.remove(queue)

    async def publish(self, event: RunStepEvent) -> None:
        async with self._lock:
            subs = list(self._subscribers.get(event.run_id, []))
        for queue in subs:
            await queue.put(event)

    async def close_run(self, run_id: str) -> None:
        """Emit a run_complete sentinel event, then signal all subscribers to stop."""
        # Emit a sentinel message so the frontend can detect completion via onmessage
        # rather than relying on polling or WebSocket close codes (which can be missed).
        sentinel = RunStepEvent(
            run_id=run_id,
            step_id=f"{run_id}-run-complete",
            parent_step_id=None,
            arm="plan_execute_synthesis",  # arm doesn't matter for sentinel
            type="run_complete",
            status="success",
            title="Run complete",
            started_at=utc_now_iso(),
            ended_at=utc_now_iso(),
            payload=StepPayload(),
        )
        async with self._lock:
            subs = list(self._subscribers.get(run_id, []))
        for queue in subs:
            await queue.put(sentinel)

        # Now send the None terminator to stop the async generator
        async with self._lock:
            subs = list(self._subscribers.get(run_id, []))
        for queue in subs:
            await queue.put(None)


event_bus = RunEventBus()
