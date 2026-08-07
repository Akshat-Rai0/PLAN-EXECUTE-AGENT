from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncIterator

from .models import RunStepEvent


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
        async with self._lock:
            subs = list(self._subscribers.get(run_id, []))
        for queue in subs:
            await queue.put(None)


event_bus = RunEventBus()
