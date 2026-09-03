"""
routers/models_router.py — Endpoints for listing available models and model-specific deep metrics.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import ProviderConfig, RequestLog
from services.aggregator import aggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models(
    provider: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Query available models across all enabled providers and merge with real usage stats.
    """
    stmt = select(ProviderConfig).where(ProviderConfig.enabled == True)
    if provider:
        stmt = stmt.where(ProviderConfig.name == provider.lower())
    providers = (await db.execute(stmt)).scalars().all()

    # Query DB stats for past 30 days
    month_start = datetime.now(timezone.utc) - timedelta(days=30)
    q_stats = (
        select(
            RequestLog.model,
            RequestLog.provider,
            func.count(RequestLog.id).label("requests"),
            func.sum(func.coalesce(RequestLog.input_tokens, 0)).label("input_tokens"),
            func.sum(func.coalesce(RequestLog.output_tokens, 0)).label("output_tokens"),
            func.sum(func.coalesce(RequestLog.total_tokens, 0)).label("total_tokens"),
            func.sum(func.coalesce(RequestLog.cost_total, 0.0)).label("cost"),
            func.avg(RequestLog.latency_ms).label("avg_latency"),
            func.sum(
                case(
                    (RequestLog.status_code >= 400, 1),
                    (RequestLog.status_code.is_(None), 1),
                    else_=0,
                )
            ).label("errors"),
            func.max(RequestLog.timestamp).label("last_used"),
        )
        .where(RequestLog.timestamp >= month_start)
        .group_by(RequestLog.model, RequestLog.provider)
    )
    db_stats_rows = (await db.execute(q_stats)).all()
    stats_map = {
        (r.provider.lower(), r.model.lower()): r
        for r in db_stats_rows
    }

    # Fetch live models from adapters
    tasks = []
    for p in providers:
        adapter = aggregator.get_adapter(p.name.lower())
        if adapter:
            tasks.append(adapter.get_models())

    models_list = []
    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                for m in res:
                    key = (m.provider.lower(), m.id.lower())
                    st = stats_map.get(key)

                    reqs = st.requests if st else 0
                    errs = st.errors if st else 0
                    models_list.append({
                        "id": m.id,
                        "name": m.name,
                        "provider": m.provider,
                        "contextWindow": m.context_window,
                        "maxTokens": m.max_tokens,
                        "inputPrice1M": m.input_price_per_1m,
                        "outputPrice1M": m.output_price_per_1m,
                        "requests": reqs,
                        "inputTokens": int(st.input_tokens or 0) if st else 0,
                        "outputTokens": int(st.output_tokens or 0) if st else 0,
                        "totalTokens": int(st.total_tokens or 0) if st else 0,
                        "cost": round(float(st.cost or 0.0), 4) if (st and st.cost) else None,
                        "latency": round(float(st.avg_latency or 0.0), 1) if (st and st.avg_latency) else None,
                        "errors": errs,
                        "errorRate": round(errs / reqs, 4) if reqs > 0 else 0.0,
                        "lastUsed": st.last_used.isoformat() if (st and st.last_used) else None,
                        "available": m.available,
                    })

    # If no adapters returned models, fallback to models found in DB
    if not models_list and db_stats_rows:
        for r in db_stats_rows:
            models_list.append({
                "id": r.model,
                "name": r.model,
                "provider": r.provider,
                "contextWindow": None,
                "maxTokens": None,
                "inputPrice1M": None,
                "outputPrice1M": None,
                "requests": r.requests,
                "inputTokens": int(r.input_tokens or 0),
                "outputTokens": int(r.output_tokens or 0),
                "totalTokens": int(r.total_tokens or 0),
                "cost": round(float(r.cost or 0.0), 4) if r.cost else None,
                "latency": round(float(r.avg_latency or 0.0), 1) if r.avg_latency else None,
                "errors": r.errors or 0,
                "errorRate": round((r.errors or 0) / r.requests, 4) if r.requests > 0 else 0.0,
                "lastUsed": r.last_used.isoformat() if r.last_used else None,
                "available": True,
            })

    return models_list


@router.get("/{provider}/{model_id:path}")
async def get_model_detail(
    provider: str,
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Deep metrics and percentiles for a specific model."""
    clean_provider = provider.lower()
    
    # Query all requests for this model
    q = (
        select(RequestLog)
        .where(
            RequestLog.provider == clean_provider,
            RequestLog.model == model_id,
        )
        .order_by(RequestLog.timestamp.desc())
    )
    logs = (await db.execute(q)).scalars().all()

    total_reqs = len(logs)
    if total_reqs == 0:
        # Check if adapter knows the model metadata
        adapter = aggregator.get_adapter(clean_provider)
        meta = None
        if adapter:
            models = await adapter.get_models()
            meta = next((m for m in models if m.id == model_id), None)

        return {
            "model": model_id,
            "provider": clean_provider,
            "overview": {
                "name": meta.name if meta else model_id,
                "status": "ONLINE" if meta else "UNKNOWN",
                "contextWindow": meta.context_window if meta else None,
                "maxTokens": meta.max_tokens if meta else None,
            },
            "usage": {
                "requests": 0,
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
            },
            "performance": {
                "avgLatency": None,
                "p50": None,
                "p95": None,
                "p99": None,
            },
            "reliability": {
                "successRate": 1.0,
                "errorRate": 0.0,
                "timeouts": 0,
            },
            "limits": {
                "rpm": 500,
                "tpm": 100000,
                "rpd": None,
                "tpd": None,
            },
            "cost": {
                "inputCost": None,
                "outputCost": None,
                "totalCost": None,
                "inputPrice1M": meta.input_price_per_1m if meta else None,
                "outputPrice1M": meta.output_price_per_1m if meta else None,
            },
        }

    # Aggregate real logs
    latencies = [l.latency_ms for l in logs if l.latency_ms is not None]
    latencies.sort()
    
    def _pct(arr, p):
        if not arr:
            return None
        k = (len(arr) - 1) * p
        f = int(k)
        c = int(min(f + 1, len(arr) - 1))
        d = k - f
        return round(arr[f] + d * (arr[c] - arr[f]), 1)

    errors = sum(1 for l in logs if (l.status_code and l.status_code >= 400) or l.status_code is None)
    timeouts = sum(1 for l in logs if l.status_code in (408, 504))

    total_in = sum(l.input_tokens or 0 for l in logs)
    total_out = sum(l.output_tokens or 0 for l in logs)
    total_tok = sum(l.total_tokens or 0 for l in logs)
    cost_in = sum(l.cost_input or 0.0 for l in logs)
    cost_out = sum(l.cost_output or 0.0 for l in logs)
    cost_tot = sum(l.cost_total or 0.0 for l in logs)

    return {
        "model": model_id,
        "provider": clean_provider,
        "overview": {
            "name": model_id,
            "status": "ONLINE",
            "contextWindow": None,
            "maxTokens": None,
        },
        "usage": {
            "requests": total_reqs,
            "inputTokens": total_in,
            "outputTokens": total_out,
            "totalTokens": total_tok,
        },
        "performance": {
            "avgLatency": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "p50": _pct(latencies, 0.50),
            "p95": _pct(latencies, 0.95),
            "p99": _pct(latencies, 0.99),
        },
        "reliability": {
            "successRate": round((total_reqs - errors) / total_reqs, 4),
            "errorRate": round(errors / total_reqs, 4),
            "timeouts": timeouts,
        },
        "limits": {
            "rpm": 500,
            "tpm": 100000,
            "rpd": None,
            "tpd": None,
        },
        "cost": {
            "inputCost": round(cost_in, 4) if cost_in > 0 else None,
            "outputCost": round(cost_out, 4) if cost_out > 0 else None,
            "totalCost": round(cost_tot, 4) if cost_tot > 0 else None,
        },
    }
