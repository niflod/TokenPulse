"""
services/aggregator.py — Central aggregation and adapter orchestration service.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.anthropic_adapter import AnthropicAdapter
from adapters.base import HealthStatus, ModelInfo, NormalizedUsage, ProviderAdapter
from adapters.gemini_adapter import GeminiAdapter
from adapters.openai_adapter import OpenAIAdapter
from config import settings
from models import ProviderConfig, RequestLog
from services.projection import calculate_burn_rate

logger = logging.getLogger(__name__)


class AggregatorService:
    """Manages adapter instances, in-memory cache, and SQL query aggregations."""

    def __init__(self):
        self._adapters: Dict[str, ProviderAdapter] = {}
        self._cache: Dict[str, tuple[Any, float]] = {}  # key -> (data, expire_timestamp)

    def register_provider(
        self, name: str, api_key: Optional[str] = None, base_url: Optional[str] = None
    ) -> Optional[ProviderAdapter]:
        """Instantiate and register an adapter for a provider."""
        adapter: Optional[ProviderAdapter] = None
        clean_name = name.lower().strip()

        if clean_name == "openai":
            adapter = OpenAIAdapter(api_key=api_key, base_url=base_url)
        elif clean_name == "anthropic":
            adapter = AnthropicAdapter(api_key=api_key, base_url=base_url)
        elif clean_name == "gemini":
            adapter = GeminiAdapter(api_key=api_key, base_url=base_url)

        if adapter:
            self._adapters[clean_name] = adapter
            logger.info("Registered provider adapter: %s", clean_name)
        return adapter

    def get_adapter(self, name: str) -> Optional[ProviderAdapter]:
        return self._adapters.get(name.lower().strip())

    def unregister_provider(self, name: str) -> None:
        self._adapters.pop(name.lower().strip(), None)

    def get_registered_providers(self) -> List[str]:
        return list(self._adapters.keys())

    # Cache helper
    def get_cached(self, key: str) -> Optional[Any]:
        if key in self._cache:
            data, expires_at = self._cache[key]
            if time.time() < expires_at:
                return data
            else:
                del self._cache[key]
        return None

    def set_cached(self, key: str, data: Any, ttl_seconds: int = 30) -> None:
        self._cache[key] = (data, time.time() + ttl_seconds)

    # -------------------------------------------------------------------------
    # Database Metrics Aggregation
    # -------------------------------------------------------------------------

    async def get_metrics_summary(
        self,
        db: AsyncSession,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict:
        """
        Aggregate usage for Today, Week, Month and group by Model and Provider.
        Includes percentiles, burn rate projections, and rate limit status.
        """
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

        # Elapsed hours today
        elapsed_hours = max((now - today_start).total_seconds() / 3600.0, 0.1)

        async def _query_period(start_dt: datetime):
            q = select(
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
            ).where(RequestLog.timestamp >= start_dt)

            if provider:
                q = q.where(RequestLog.provider == provider)
            if model:
                q = q.where(RequestLog.model == model)

            res = (await db.execute(q)).one()
            reqs = res.requests or 0
            errs = res.errors or 0
            return {
                "requests": reqs,
                "inputTokens": int(res.input_tokens or 0),
                "outputTokens": int(res.output_tokens or 0),
                "totalTokens": int(res.total_tokens or 0),
                "cost": round(float(res.cost or 0.0), 4) if res.cost is not None else None,
                "avgLatencyMs": round(float(res.avg_latency or 0.0), 1) if res.avg_latency else None,
                "errors": errs,
                "errorRate": round(errs / reqs, 4) if reqs > 0 else 0.0,
            }

        today_metrics = await _query_period(today_start)
        week_metrics = await _query_period(week_start)
        month_metrics = await _query_period(month_start)

        # Group by Model (past 30 days)
        q_models = (
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
            .order_by(func.count(RequestLog.id).desc())
        )
        if provider:
            q_models = q_models.where(RequestLog.provider == provider)

        res_models = (await db.execute(q_models)).all()
        by_model = [
            {
                "model": r.model,
                "provider": r.provider,
                "requests": r.requests,
                "inputTokens": int(r.input_tokens or 0),
                "outputTokens": int(r.output_tokens or 0),
                "totalTokens": int(r.total_tokens or 0),
                "cost": round(float(r.cost or 0.0), 4) if r.cost is not None else None,
                "latency": round(float(r.avg_latency or 0.0), 1) if r.avg_latency else None,
                "errors": r.errors or 0,
                "errorRate": round((r.errors or 0) / r.requests, 4) if r.requests > 0 else 0.0,
                "lastUsed": r.last_used.isoformat() if r.last_used else None,
            }
            for r in res_models
        ]

        # Group by Provider (past 30 days)
        q_providers = (
            select(
                RequestLog.provider,
                func.count(RequestLog.id).label("requests"),
                func.sum(func.coalesce(RequestLog.input_tokens, 0)).label("input_tokens"),
                func.sum(func.coalesce(RequestLog.output_tokens, 0)).label("output_tokens"),
                func.sum(func.coalesce(RequestLog.total_tokens, 0)).label("total_tokens"),
                func.sum(func.coalesce(RequestLog.cost_total, 0.0)).label("cost"),
                func.avg(RequestLog.latency_ms).label("avg_latency"),
            )
            .where(RequestLog.timestamp >= month_start)
            .group_by(RequestLog.provider)
        )
        res_providers = (await db.execute(q_providers)).all()
        by_provider = [
            {
                "provider": r.provider,
                "requests": r.requests,
                "inputTokens": int(r.input_tokens or 0),
                "outputTokens": int(r.output_tokens or 0),
                "totalTokens": int(r.total_tokens or 0),
                "cost": round(float(r.cost or 0.0), 4) if r.cost is not None else None,
                "latency": round(float(r.avg_latency or 0.0), 1) if r.avg_latency else None,
            }
            for r in res_providers
        ]

        # Default standard limits (can be configured or returned by providers)
        # If no custom limit is set, default to None or standard tiers
        limits = {
            "daily": 10000 if not provider else 5000,
            "weekly": 70000 if not provider else 35000,
            "monthly": 300000 if not provider else 150000,
            "dailyTokens": 5000000,
            "rpm": 500,
            "tpm": 100000,
        }

        # Calculate burn rate & projections
        projection = calculate_burn_rate(
            requests_today=today_metrics["requests"],
            tokens_today=today_metrics["totalTokens"],
            cost_today=today_metrics["cost"],
            elapsed_hours_today=elapsed_hours,
            daily_request_limit=limits["daily"],
            daily_token_limit=limits["dailyTokens"],
        )

        return {
            "summary": {
                "today": today_metrics,
                "week": week_metrics,
                "month": month_metrics,
            },
            "limits": limits,
            "projection": projection,
            "byModel": by_model,
            "byProvider": by_provider,
            "serverTime": now.isoformat(),
        }

    async def get_timeseries(
        self,
        db: AsyncSession,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        hours: int = 24,
    ) -> list[dict]:
        """
        Generate hourly aggregated points for the charts.
        Uses SQL GROUP BY for O(1) memory regardless of data volume.
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        # SQLite strftime groups by hour-truncated UTC timestamp
        hour_bucket = func.strftime("%Y-%m-%dT%H:00:00Z", RequestLog.timestamp)

        q = (
            select(
                hour_bucket.label("bucket"),
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
            )
            .where(RequestLog.timestamp >= start_time)
            .group_by(hour_bucket)
            .order_by(hour_bucket)
        )

        if provider:
            q = q.where(RequestLog.provider == provider)
        if model:
            q = q.where(RequestLog.model == model)

        rows = (await db.execute(q)).all()

        # Build lookup from SQL results
        sql_buckets: Dict[str, dict] = {}
        for r in rows:
            sql_buckets[r.bucket] = {
                "requests": r.requests or 0,
                "inputTokens": int(r.input_tokens or 0),
                "outputTokens": int(r.output_tokens or 0),
                "totalTokens": int(r.total_tokens or 0),
                "cost": round(float(r.cost), 4) if r.cost else None,
                "latency": round(float(r.avg_latency), 1) if r.avg_latency else None,
                "errors": r.errors or 0,
            }

        # Pre-populate all hours so chart has complete X-axis (zero-filled)
        result = []
        for h in range(hours):
            t = start_time + timedelta(hours=h)
            bucket_key = t.strftime("%Y-%m-%dT%H:00:00Z")
            entry = sql_buckets.get(bucket_key, {
                "requests": 0,
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
                "cost": None,
                "latency": None,
                "errors": 0,
            })
            result.append({"timestamp": bucket_key, **entry})

        return result


# Global aggregator instance
aggregator = AggregatorService()
