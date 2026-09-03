"""
routers/realtime.py — Server-Sent Events (SSE) stream for live TokenPulse telemetry.
Listens to real-time events via EventBus and provides a periodic 5s heartbeat/summary fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from database import AsyncSessionLocal
from services.aggregator import aggregator
from services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


async def event_generator() -> AsyncGenerator[str, None]:
    """
    Streams telemetry events from EventBus immediately when requests complete,
    and falls back to periodic summary ticks every 5 seconds.
    """
    queue = event_bus.subscribe()
    try:
        while True:
            try:
                # 1. Wait up to 5 seconds for a real-time event (e.g. request.completed)
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            except asyncio.TimeoutError:
                # 2. Periodic tick every 5 seconds with updated metrics summary
                try:
                    async with AsyncSessionLocal() as db:
                        metrics = await aggregator.get_metrics_summary(db)

                    data = {
                        "type": "metrics_tick",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "summary": metrics.get("summary"),
                        "projection": metrics.get("projection"),
                        "serverTime": metrics.get("serverTime"),
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                except Exception as exc:
                    logger.warning("SSE tick error: %s", exc)
                    yield f"event: heartbeat\ndata: {{}}\n\n"
    except asyncio.CancelledError:
        logger.debug("SSE client disconnected.")
    finally:
        event_bus.unsubscribe(queue)


@router.get("/stream")
async def realtime_stream():
    """Server-Sent Events (SSE) telemetry stream."""
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
