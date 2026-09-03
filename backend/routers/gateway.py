"""
routers/gateway.py — TokenPulse Gateway / SDK Telemetry Ingestion Endpoint.
Architecture:
    Application -> TokenPulse SDK/Gateway Proxy -> Provider (OpenAI, Anthropic, Gemini)
                       |
                       +-> POST /api/v1/telemetry (Automatic observability)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import RequestLog
from pricing import lookup_pricing
from security import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

SupportedProvider = Literal["openai", "anthropic", "gemini"]


class TelemetryEvent(BaseModel):
    provider: SupportedProvider
    model: str = Field(..., min_length=1, max_length=128)
    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    total_tokens: Optional[int] = Field(None, ge=0)
    latency_ms: Optional[float] = Field(None, ge=0.0)
    status_code: Optional[int] = Field(200, ge=100, le=599)
    error_message: Optional[str] = None
    request_id: Optional[str] = Field(None, max_length=256)
    timestamp: Optional[datetime] = None


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def ingest_telemetry(data: TelemetryEvent, db: AsyncSession = Depends(get_db)):
    """
    Ingest a telemetry event from the TokenPulse SDK or Gateway Proxy.
    Automatically calculates costs via the centralized pricing registry if omitted.
    """
    tot_tok = data.total_tokens
    if tot_tok is None and data.input_tokens is not None and data.output_tokens is not None:
        tot_tok = data.input_tokens + data.output_tokens

    # Automatic cost derivation from pricing catalog
    inp_price, out_price, _, _ = lookup_pricing(data.provider, data.model)
    cost_in = None
    cost_out = None
    cost_tot = None

    if inp_price is not None and data.input_tokens is not None:
        cost_in = (data.input_tokens / 1_000_000) * inp_price
    if out_price is not None and data.output_tokens is not None:
        cost_out = (data.output_tokens / 1_000_000) * out_price
    if cost_in is not None or cost_out is not None:
        cost_tot = round((cost_in or 0.0) + (cost_out or 0.0), 6)

    event_time = data.timestamp or datetime.now(timezone.utc)

    log_entry = RequestLog(
        provider=data.provider.lower(),
        model=data.model,
        timestamp=event_time,
        input_tokens=data.input_tokens,
        output_tokens=data.output_tokens,
        total_tokens=tot_tok,
        latency_ms=data.latency_ms,
        status_code=data.status_code,
        error_message=data.error_message,
        cost_input=round(cost_in, 6) if cost_in is not None else None,
        cost_output=round(cost_out, 6) if cost_out is not None else None,
        cost_total=cost_tot,
        request_id=data.request_id,
    )

    db.add(log_entry)
    await db.flush()

    return {
        "status": "ingested",
        "log_id": log_entry.id,
        "estimated_cost_usd": cost_tot,
    }
