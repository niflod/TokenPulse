"""
services/anomaly.py — Anomaly detection engine for AI API usage.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import RequestLog

logger = logging.getLogger(__name__)


async def detect_anomalies(
    db: AsyncSession,
    window_minutes: int = 15,
    baseline_minutes: int = 60,
    threshold_multiplier: float = 2.0,
) -> List[dict]:
    """
    Detect spikes in requests, tokens, error rates, and latencies
    by comparing recent activity with earlier baseline window.
    """
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(minutes=window_minutes)
    baseline_start = now - timedelta(minutes=baseline_minutes)

    anomalies: List[dict] = []

    try:
        # 1. Query metrics for Recent window
        q_recent = (
            select(
                RequestLog.provider,
                RequestLog.model,
                func.count(RequestLog.id).label("req_count"),
                func.sum(func.coalesce(RequestLog.total_tokens, 0)).label("total_tokens"),
                func.sum(
                    case(
                        (RequestLog.status_code >= 400, 1),
                        (RequestLog.status_code.is_(None), 1),
                        else_=0,
                    )
                ).label("err_count"),
                func.avg(RequestLog.latency_ms).label("avg_latency"),
            )
            .where(RequestLog.timestamp >= recent_start)
            .group_by(RequestLog.provider, RequestLog.model)
        )
        res_recent = (await db.execute(q_recent)).all()

        # 2. Query metrics for Baseline window
        q_base = (
            select(
                RequestLog.provider,
                RequestLog.model,
                func.count(RequestLog.id).label("req_count"),
                func.sum(func.coalesce(RequestLog.total_tokens, 0)).label("total_tokens"),
                func.sum(
                    case(
                        (RequestLog.status_code >= 400, 1),
                        (RequestLog.status_code.is_(None), 1),
                        else_=0,
                    )
                ).label("err_count"),
                func.avg(RequestLog.latency_ms).label("avg_latency"),
            )
            .where(RequestLog.timestamp >= baseline_start, RequestLog.timestamp < recent_start)
            .group_by(RequestLog.provider, RequestLog.model)
        )
        res_base = (await db.execute(q_base)).all()

        base_map = {
            (r.provider, r.model): {
                "req_rate": r.req_count / max(1, (baseline_minutes - window_minutes)),
                "token_rate": (r.total_tokens or 0) / max(1, (baseline_minutes - window_minutes)),
                "err_rate": (r.err_count or 0) / max(1, r.req_count),
                "avg_latency": r.avg_latency or 0.0,
            }
            for r in res_base
        }

        # Compare recent to baseline
        for r in res_recent:
            key = (r.provider, r.model)
            recent_req_rate = r.req_count / window_minutes
            recent_token_rate = (r.total_tokens or 0) / window_minutes
            recent_err_rate = (r.err_count or 0) / max(1, r.req_count)
            recent_lat = r.avg_latency or 0.0

            base = base_map.get(key)
            if not base:
                # If high volume on brand new model, alert if requests > 50 in window
                if r.req_count > 50:
                    anomalies.append({
                        "type": "requests",
                        "provider": r.provider,
                        "model": r.model,
                        "severity": "warning",
                        "message": f"Novo fluxo detectado: {r.model} com {r.req_count} requisições nos últimos {window_minutes}m.",
                        "change_pct": 100.0,
                        "detected_at": now.isoformat(),
                    })
                continue

            # Token spike check
            if base["token_rate"] > 10 and recent_token_rate >= base["token_rate"] * threshold_multiplier:
                pct = round(((recent_token_rate - base["token_rate"]) / base["token_rate"]) * 100, 1)
                anomalies.append({
                    "type": "tokens",
                    "provider": r.provider,
                    "model": r.model,
                    "severity": "warning" if pct < 300 else "critical",
                    "message": f"O modelo {r.model} apresentou aumento de +{pct}% no consumo de tokens nos últimos {window_minutes} minutos.",
                    "change_pct": pct,
                    "detected_at": now.isoformat(),
                })

            # Error rate spike check
            if recent_err_rate > 0.15 and recent_err_rate > (base["err_rate"] * 1.5 + 0.05):
                err_pct = round(recent_err_rate * 100, 1)
                anomalies.append({
                    "type": "errors",
                    "provider": r.provider,
                    "model": r.model,
                    "severity": "critical",
                    "message": f"Taxa de erro de {err_pct}% detectada para {r.model} nos últimos {window_minutes}m.",
                    "change_pct": round(recent_err_rate * 100, 1),
                    "detected_at": now.isoformat(),
                })

            # Latency spike check
            if base["avg_latency"] > 100 and recent_lat > (base["avg_latency"] * threshold_multiplier) and recent_lat > 2000:
                lat_pct = round(((recent_lat - base["avg_latency"]) / base["avg_latency"]) * 100, 1)
                anomalies.append({
                    "type": "latency",
                    "provider": r.provider,
                    "model": r.model,
                    "severity": "warning",
                    "message": f"Latência média do modelo {r.model} subiu +{lat_pct}% ({round(recent_lat)}ms) recentemente.",
                    "change_pct": lat_pct,
                    "detected_at": now.isoformat(),
                })

    except Exception as exc:
        logger.error("Error during anomaly detection: %s", exc)

    return anomalies
