"""
routers/logs.py — Paginated request log query and recording endpoints.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import RequestLog
from security import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/logs", tags=["logs"])

SupportedProvider = Literal["openai", "anthropic", "gemini"]


class RequestLogIn(BaseModel):
    provider: SupportedProvider
    model: str = Field(..., min_length=1, max_length=128)
    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    total_tokens: Optional[int] = Field(None, ge=0)
    latency_ms: Optional[float] = Field(None, ge=0.0)
    status_code: Optional[int] = Field(200, ge=100, le=599)
    error_message: Optional[str] = None
    cost_input: Optional[float] = Field(None, ge=0.0)
    cost_output: Optional[float] = Field(None, ge=0.0)
    cost_total: Optional[float] = Field(None, ge=0.0)
    request_id: Optional[str] = Field(None, max_length=256)


class RequestLogOut(BaseModel):
    id: int
    provider: str
    model: str
    timestamp: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    cost_total: Optional[float] = None
    request_id: Optional[str] = None
    time_to_first_token_ms: Optional[float] = None
    stream_duration_ms: Optional[float] = None
    cached_input_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    provider_request_id: Optional[str] = None


@router.get("")
async def get_logs(
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Query paginated request logs with optional filters."""
    q = select(RequestLog).order_by(RequestLog.timestamp.desc())
    count_q = select(func.count(RequestLog.id))

    if provider:
        q = q.where(RequestLog.provider == provider.lower())
        count_q = count_q.where(RequestLog.provider == provider.lower())
    if model:
        q = q.where(RequestLog.model == model)
        count_q = count_q.where(RequestLog.model == model)
    if status_filter:
        if status_filter == "error":
            q = q.where((RequestLog.status_code >= 400) | (RequestLog.status_code.is_(None)))
            count_q = count_q.where((RequestLog.status_code >= 400) | (RequestLog.status_code.is_(None)))
        elif status_filter == "success":
            q = q.where((RequestLog.status_code >= 200) & (RequestLog.status_code < 400))
            count_q = count_q.where((RequestLog.status_code >= 200) & (RequestLog.status_code < 400))

    total = (await db.execute(count_q)).scalar_one()
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

    items = [
        RequestLogOut(
            id=r.id,
            provider=r.provider,
            model=r.model,
            timestamp=r.timestamp.isoformat() if r.timestamp else "",
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            total_tokens=r.total_tokens,
            latency_ms=round(r.latency_ms, 1) if r.latency_ms is not None else None,
            status_code=r.status_code,
            error_message=r.error_message,
            cost_total=round(r.cost_total, 4) if r.cost_total is not None else None,
            request_id=r.request_id,
            time_to_first_token_ms=r.time_to_first_token_ms,
            stream_duration_ms=r.stream_duration_ms,
            cached_input_tokens=r.cached_input_tokens,
            reasoning_tokens=r.reasoning_tokens,
            finish_reason=r.finish_reason,
            provider_request_id=r.provider_request_id,
        )
        for r in rows
    ]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def record_log(data: RequestLogIn, db: AsyncSession = Depends(get_db)):
    """Record a single request log entry with strict input validation."""
    tot_tok = data.total_tokens
    if tot_tok is None and data.input_tokens is not None and data.output_tokens is not None:
        tot_tok = data.input_tokens + data.output_tokens

    tot_cost = data.cost_total
    if tot_cost is None and data.cost_input is not None and data.cost_output is not None:
        tot_cost = round(data.cost_input + data.cost_output, 6)

    entry = RequestLog(
        provider=data.provider.lower(),
        model=data.model,
        timestamp=datetime.now(timezone.utc),
        input_tokens=data.input_tokens,
        output_tokens=data.output_tokens,
        total_tokens=tot_tok,
        latency_ms=data.latency_ms,
        status_code=data.status_code,
        error_message=data.error_message,
        cost_input=data.cost_input,
        cost_output=data.cost_output,
        cost_total=tot_cost,
        request_id=data.request_id,
    )
    db.add(entry)
    await db.flush()
    return {"status": "created", "id": entry.id}


@router.delete("", dependencies=[Depends(require_admin)])
async def clear_logs(
    confirm: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Efficient bulk clear of request logs via direct SQL DELETE."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="É necessário passar ?confirm=true para apagar todos os logs.",
        )
    await db.execute(delete(RequestLog))
    return {"message": "Todos os logs foram apagados com sucesso."}


@router.post("/prune", dependencies=[Depends(require_admin)])
async def prune_old_logs(
    days: Optional[int] = Query(None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    """Prune logs older than configured retention period (Requisito 35)."""
    from datetime import timedelta
    from config import settings

    retention_days = days or settings.log_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    stmt = delete(RequestLog).where(RequestLog.timestamp < cutoff)
    res = await db.execute(stmt)
    return {"status": "pruned", "retention_days": retention_days, "deleted_count": res.rowcount}

