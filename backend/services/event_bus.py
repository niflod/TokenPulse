"""
services/event_bus.py — Minimal in-memory event bus for TokenPulse real-time events.
Pub/Sub pattern for single-worker SSE broadcast (ponytail: in-memory queue, upgrade to Redis if multi-worker).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Set

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: Set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        if not self._subscribers:
            return
        payload = {"type": event_type, "version": 1, "data": data}
        dead_queues = set()
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # Discard slow consumer
                dead_queues.add(q)
        for dq in dead_queues:
            self._subscribers.discard(dq)


event_bus = EventBus()
