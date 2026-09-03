"""
routers/metrics.py — Metrics summary, timeseries, anomaly detection, and demo data endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.aggregator import aggregator
from services.anomaly import detect_anomalies
from services.demo import generate_demo_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summary")
async def get_summary(
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate total usage, costs, performance, and projection."""
    cache_key = f"summary:{provider}:{model}"
    cached = aggregator.get_cached(cache_key)
    if cached:
        return cached

    metrics = await aggregator.get_metrics_summary(db, provider=provider, model=model)
    aggregator.set_cached(cache_key, metrics, ttl_seconds=15)
    return metrics


@router.get("/timeseries")
async def get_timeseries(
    provider: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """Hourly timeseries for Chart.js rendering."""
    cache_key = f"timeseries:{provider}:{model}:{hours}"
    cached = aggregator.get_cached(cache_key)
    if cached:
        return cached

    series = await aggregator.get_timeseries(db, provider=provider, model=model, hours=hours)
    aggregator.set_cached(cache_key, series, ttl_seconds=15)
    return series


@router.get("/anomalies")
async def get_anomalies(db: AsyncSession = Depends(get_db)):
    """Run anomaly detection on recent request volume, tokens, and errors."""
    return await detect_anomalies(db, window_minutes=15, baseline_minutes=60)


@router.get("/demo")
async def get_demo_metrics():
    """
    Generate complete, realistic observability data for Demo Mode.
    Delegated cleanly to isolated demo service.
    """
    return generate_demo_data()
