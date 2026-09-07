from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from config import settings
from database import AsyncSessionLocal
from models import User
from routers.auth import get_current_user
from security import check_auth_rate_limit
from services.aggregator import aggregator
from services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])

# In-memory single-use ticket store: {ticket: (expiry_timestamp, user_id)}
_REALTIME_TICKETS: dict[str, tuple[float, Optional[int]]] = {}


def create_stream_ticket(ttl_seconds: int = 30, user_id: Optional[int] = None) -> str:
    """Generates a secure, disposable single-use ticket for SSE connection bound to a user."""
    ticket = f"ssec_{secrets.token_hex(24)}"
    now = time.time()
    # Prune expired tickets
    expired = [k for k, (exp, _) in _REALTIME_TICKETS.items() if exp < now]
    for k in expired:
        _REALTIME_TICKETS.pop(k, None)
    _REALTIME_TICKETS[ticket] = (now + ttl_seconds, user_id)
    return ticket


def validate_and_consume_ticket(ticket: str) -> bool:
    """Consumes and invalidates a disposable stream ticket. Returns True if valid."""
    now = time.time()
    entry = _REALTIME_TICKETS.pop(ticket, None)
    if entry:
        exp, _ = entry
        return exp >= now
    return False


def consume_stream_ticket(ticket: str) -> tuple[bool, Optional[int]]:
    """Consumes ticket and returns (is_valid, user_id)."""
    now = time.time()
    entry = _REALTIME_TICKETS.pop(ticket, None)
    if entry:
        exp, uid = entry
        if exp >= now:
            return True, uid
    return False, None


@router.post("/ticket")
async def request_realtime_ticket(request: Request, user: User = Depends(get_current_user)):
    """Generates a single-use ticket (30s) bound to authenticated user for SSE connection."""
    check_auth_rate_limit(request, action="ticket", custom_rpm=settings.auth_rate_limit_rpm)
    ticket = create_stream_ticket(ttl_seconds=30, user_id=user.id)
    return {"ticket": ticket, "expires_in": 30, "user_id": user.id}


async def event_generator(user_id: Optional[int] = None) -> AsyncGenerator[str, None]:
    """
    Streams telemetry events from EventBus filtered by tenant identity,
    and falls back to periodic summary ticks every 5 seconds scoped by user_id.
    """
    queue = event_bus.subscribe()
    try:
        while True:
            try:
                # 1. Wait up to 5 seconds for a real-time event (e.g. request.completed)
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
                event_data = event.get("data", {})
                event_user_id = event_data.get("user_id")

                # Discard telemetry belonging to other tenants
                if user_id is not None and event_user_id is not None and event_user_id != user_id:
                    continue

                yield f"event: {event['type']}\ndata: {json.dumps(event_data)}\n\n"
            except asyncio.TimeoutError:
                # 2. Periodic tick every 5 seconds with updated metrics summary scoped by user_id
                try:
                    async with AsyncSessionLocal() as db:
                        metrics = await aggregator.get_metrics_summary(db, user_id=user_id)

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
async def realtime_stream(request: Request):
    """Server-Sent Events (SSE) telemetry stream scoped to the caller's tenant identity."""
    user_id = getattr(request.state, "user_id", None)
    return StreamingResponse(
        event_generator(user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
