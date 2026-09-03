"""
routers/realtime.py — Server-Sent Events (SSE) stream for live TokenPulse telemetry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.aggregator import aggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/realtime", tags=["realtime"])


async def event_generator(db: AsyncSession) -> AsyncGenerator[str, None]:
    """
    Streams telemetry heartbeats and metric updates over SSE.
    """
    try:
        while True:
            # Fetch current metrics
            metrics = await aggregator.get_metrics_summary(db)
            data = {
                "type": "metrics_tick",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": metrics.get("summary"),
                "projection": metrics.get("projection"),
                "serverTime": metrics.get("serverTime"),
            }
            yield f"data: {json.dumps(data)}\n\n"
            # Sleep 5 seconds between ticks
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        logger.debug("SSE client disconnected.")


@router.get("/stream")
async def realtime_stream(db: AsyncSession = Depends(get_db)):
    """Server-Sent Events (SSE) telemetry stream."""
    return StreamingResponse(
        event_generator(db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
