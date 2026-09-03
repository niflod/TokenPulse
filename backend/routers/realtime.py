from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from database import AsyncSessionLocal
from services.aggregator import aggregator
from services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

# In-memory single-use ticket store: {ticket: expiry_timestamp}
_REALTIME_TICKETS: dict[str, float] = {}


def create_stream_ticket(ttl_seconds: int = 30) -> str:
    """Generates a secure, disposable single-use ticket for SSE connection."""
    ticket = f"ssec_{secrets.token_hex(24)}"
    now = time.time()
    # Prune expired tickets
    expired = [k for k, exp in _REALTIME_TICKETS.items() if exp < now]
    for k in expired:
        _REALTIME_TICKETS.pop(k, None)
    _REALTIME_TICKETS[ticket] = now + ttl_seconds
    return ticket


def validate_and_consume_ticket(ticket: str) -> bool:
    """Consumes and invalidates a disposable stream ticket. Returns True if valid."""
    now = time.time()
    expiry = _REALTIME_TICKETS.pop(ticket, None)
    if expiry and expiry >= now:
        return True
    return False


@router.post("/ticket")
async def request_realtime_ticket():
    """Generates a single-use ticket (30s) for establishing SSE connection without JWT in query string."""
    ticket = create_stream_ticket(ttl_seconds=30)
    return {"ticket": ticket, "expires_in": 30}


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
