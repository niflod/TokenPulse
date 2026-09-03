"""
services/demo.py — Isolated generator for realistic TokenPulse demo data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def generate_demo_data() -> dict:
    """
    Generate realistic observability data for Demo Mode.
    Clearly flagged with 'demo: True'. Never uses real credentials.
    """
    now = datetime.now(timezone.utc)

    # 24-hour timeline generator
    timeseries = []
    for i in range(24, 0, -1):
        t = now - timedelta(hours=i)
        hour = t.hour
        # Natural traffic curve with peak during business hours
        base_reqs = 180 + int(240 * (0.5 + 0.5 * (1 - abs(hour - 15) / 12)))
        tokens = base_reqs * 1450
        cost = round((tokens / 1_000_000) * 3.20, 3)
        lat = 650 + int(200 * (hour % 5) / 4)
        errs = 1 if hour == 14 else 0
        timeseries.append({
            "timestamp": t.strftime("%Y-%m-%dT%H:00:00Z"),
            "requests": base_reqs,
            "inputTokens": int(tokens * 0.72),
            "outputTokens": int(tokens * 0.28),
            "totalTokens": tokens,
            "cost": cost,
            "latency": lat,
            "errors": errs,
        })

    return {
        "demo": True,
        "serverTime": now.isoformat(),
        "summary": {
            "today": {
                "requests": 6840,
                "inputTokens": 6780000,
                "outputTokens": 2630000,
                "totalTokens": 9410000,
                "cost": 18.4500,
                "avgLatencyMs": 745.2,
                "errors": 24,
                "errorRate": 0.0035,
            },
            "week": {
                "requests": 42100,
                "inputTokens": 41200000,
                "outputTokens": 16400000,
                "totalTokens": 57600000,
                "cost": 114.8000,
                "avgLatencyMs": 720.0,
                "errors": 112,
                "errorRate": 0.0027,
            },
            "month": {
                "requests": 158400,
                "inputTokens": 154000000,
                "outputTokens": 61200000,
                "totalTokens": 215200000,
                "cost": 428.6000,
                "avgLatencyMs": 710.5,
                "errors": 390,
                "errorRate": 0.0025,
            },
        },
        "limits": {
            "daily": 10000,
            "weekly": 70000,
            "monthly": 300000,
            "dailyTokens": 15000000,
            "rpm": 500,
            "tpm": 150000,
        },
        "projection": {
            "requestsPerHour": 380.0,
            "tokensPerHour": 522777.8,
            "costPerHour": 1.025,
            "projectedDailyRequests": 9120,
            "projectedDailyTokens": 12546667,
            "projectedDailyCost": 24.60,
            "projectedUtilizationPct": 91.2,
            "etaRequestsLimit": "6h 45m",
            "etaTokensLimit": "10h 20m",
        },
        "byModel": [
            {
                "model": "gpt-4o",
                "provider": "openai",
                "requests": 3420,
                "inputTokens": 3200000,
                "outputTokens": 1100000,
                "totalTokens": 4300000,
                "cost": 19.00,
                "latency": 810.0,
                "errors": 12,
                "errorRate": 0.0035,
                "lastUsed": (now - timedelta(minutes=3)).isoformat(),
            },
            {
                "model": "claude-3-5-sonnet",
                "provider": "anthropic",
                "requests": 2100,
                "inputTokens": 2200000,
                "outputTokens": 890000,
                "totalTokens": 3090000,
                "cost": 19.95,
                "latency": 920.0,
                "errors": 5,
                "errorRate": 0.0024,
                "lastUsed": (now - timedelta(minutes=7)).isoformat(),
            },
            {
                "model": "gemini-2.0-flash",
                "provider": "gemini",
                "requests": 1150,
                "inputTokens": 1100000,
                "outputTokens": 540000,
                "totalTokens": 1640000,
                "cost": 0.326,
                "latency": 340.0,
                "errors": 4,
                "errorRate": 0.0035,
                "lastUsed": (now - timedelta(minutes=1)).isoformat(),
            },
            {
                "model": "gpt-4o-mini",
                "provider": "openai",
                "requests": 170,
                "inputTokens": 280000,
                "outputTokens": 100000,
                "totalTokens": 380000,
                "cost": 0.102,
                "latency": 410.0,
                "errors": 3,
                "errorRate": 0.0176,
                "lastUsed": (now - timedelta(hours=2)).isoformat(),
            },
        ],
        "byProvider": [
            {
                "provider": "openai",
                "requests": 3590,
                "inputTokens": 3480000,
                "outputTokens": 1200000,
                "totalTokens": 4680000,
                "cost": 19.102,
                "latency": 790.0,
            },
            {
                "provider": "anthropic",
                "requests": 2100,
                "inputTokens": 2200000,
                "outputTokens": 890000,
                "totalTokens": 3090000,
                "cost": 19.95,
                "latency": 920.0,
            },
            {
                "provider": "gemini",
                "requests": 1150,
                "inputTokens": 1100000,
                "outputTokens": 540000,
                "totalTokens": 1640000,
                "cost": 0.326,
                "latency": 340.0,
            },
        ],
        "timeseries": timeseries,
        "anomalies": [
            {
                "type": "tokens",
                "provider": "openai",
                "model": "gpt-4o",
                "severity": "warning",
                "message": "O modelo gpt-4o apresentou aumento de 240% no consumo de tokens nos últimos 15 minutos.",
                "change_pct": 240.0,
                "detected_at": (now - timedelta(minutes=5)).isoformat(),
            }
        ],
    }
