"""
routers/export.py — Streaming CSV and JSON export endpoints for metrics and request logs.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import RequestLog, User
from routers.auth import get_current_user

router = APIRouter(prefix="/api/export", tags=["export"])


async def generate_csv_stream(
    db: AsyncSession,
    user_id: int,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = 5000,
) -> AsyncGenerator[str, None]:
    """Generates CSV rows in chunks scoped strictly to the authenticated tenant."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id",
        "timestamp_utc",
        "provider",
        "model",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_ms",
        "status_code",
        "cost_total_usd",
        "error_message",
        "request_id",
    ])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    # Query with stream scoped by user_id
    q = (
        select(RequestLog)
        .where(RequestLog.user_id == user_id)
        .order_by(RequestLog.timestamp.desc())
        .limit(limit)
    )
    if provider:
        q = q.where(RequestLog.provider == provider.lower())
    if model:
        q = q.where(RequestLog.model == model)

    result = await db.stream_scalars(q)
    async for r in result:
        writer.writerow([
            r.id,
            r.timestamp.isoformat() if r.timestamp else "",
            r.provider,
            r.model,
            r.input_tokens or 0,
            r.output_tokens or 0,
            r.total_tokens or 0,
            r.latency_ms or "",
            r.status_code or "",
            r.cost_total or "",
            r.error_message or "",
            r.request_id or "",
        ])
        if len(output.getvalue()) > 4096:
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    if output.getvalue():
        yield output.getvalue()


@router.get("/csv")
async def export_csv(
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export request logs as streaming CSV isolated by tenant."""
    filename = f"tokenpulse_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        generate_csv_stream(db, user_id=current_user.id, provider=provider, model=model, limit=limit),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/json")
async def export_json(
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    limit: int = Query(5000, ge=1, le=50000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export request logs as JSON scoped strictly to the authenticated tenant."""
    q = (
        select(RequestLog)
        .where(RequestLog.user_id == current_user.id)
        .order_by(RequestLog.timestamp.desc())
        .limit(limit)
    )
    if provider:
        q = q.where(RequestLog.provider == provider.lower())
    if model:
        q = q.where(RequestLog.model == model)

    rows = (await db.execute(q)).scalars().all()

    data = [
        {
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "provider": r.provider,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_tokens": r.total_tokens,
            "latency_ms": r.latency_ms,
            "status_code": r.status_code,
            "cost_total_usd": r.cost_total,
            "error_message": r.error_message,
            "request_id": r.request_id,
        }
        for r in rows
    ]

    filename = f"tokenpulse_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=json.dumps(data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
