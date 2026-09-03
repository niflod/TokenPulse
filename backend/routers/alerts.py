"""
routers/alerts.py — Alert thresholds configuration and active alerts evaluation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AlertConfig
from security import require_admin
from services.aggregator import aggregator
from services.anomaly import detect_anomalies

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertConfigIn(BaseModel):
    provider: str = "all"
    metric: str  # e.g., 'daily_usage_pct', 'weekly_usage_pct', 'error_rate', 'latency_ms'
    threshold: float
    enabled: bool = True


class AlertConfigOut(BaseModel):
    id: int
    provider: str
    metric: str
    threshold: float
    enabled: bool


@router.get("")
async def get_active_alerts(db: AsyncSession = Depends(get_db)):
    """Evaluate metric thresholds against active summary and combine with anomaly detections."""
    # 1. Fetch configured alert rules
    stmt = select(AlertConfig).where(AlertConfig.enabled == True)
    rules = (await db.execute(stmt)).scalars().all()

    # 2. Fetch current metrics summary
    metrics = await aggregator.get_metrics_summary(db)
    today = metrics["summary"]["today"]
    limits = metrics["limits"]

    active_alerts = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Evaluate each rule
    for r in rules:
        val = None
        label = ""
        severity = "warning"

        if r.metric == "daily_usage_pct" and limits.get("daily"):
            val = (today["requests"] / limits["daily"]) * 100
            label = f"Uso diário ({round(val, 1)}%) ultrapassou o limite configurado de {r.threshold}%."
            if val >= 95:
                severity = "critical"
        elif r.metric == "error_rate":
            val = today["errorRate"] * 100
            label = f"Taxa de erro de hoje ({round(val, 2)}%) está acima do limite de {r.threshold}%."
            severity = "critical"
        elif r.metric == "latency_ms" and today["avgLatencyMs"]:
            val = today["avgLatencyMs"]
            label = f"Latência média de hoje ({round(val)}ms) excedeu o limite de {round(r.threshold)}ms."

        if val is not None and val >= r.threshold:
            active_alerts.append({
                "id": f"rule-{r.id}",
                "ruleId": r.id,
                "provider": r.provider,
                "metric": r.metric,
                "currentValue": round(val, 2),
                "threshold": r.threshold,
                "severity": severity,
                "message": label,
                "triggeredAt": now_iso,
            })

    # 3. Add anomaly detections
    anomalies = await detect_anomalies(db, window_minutes=15)
    for i, a in enumerate(anomalies):
        active_alerts.append({
            "id": f"anomaly-{i}",
            "ruleId": None,
            "provider": a["provider"],
            "metric": a["type"],
            "currentValue": a.get("change_pct"),
            "threshold": None,
            "severity": a.get("severity", "warning"),
            "message": a["message"],
            "triggeredAt": a["detected_at"],
        })

    return active_alerts


@router.get("/config", response_model=List[AlertConfigOut])
async def list_alert_configs(db: AsyncSession = Depends(get_db)):
    """List all alert configuration rules."""
    stmt = select(AlertConfig).order_by(AlertConfig.id)
    rules = (await db.execute(stmt)).scalars().all()
    return [
        AlertConfigOut(
            id=r.id,
            provider=r.provider,
            metric=r.metric,
            threshold=r.threshold,
            enabled=r.enabled,
        )
        for r in rules
    ]


@router.post(
    "/config",
    response_model=AlertConfigOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_alert_config(
    data: AlertConfigIn, db: AsyncSession = Depends(get_db)
):
    """Create a new alert threshold rule."""
    rule = AlertConfig(
        provider=data.provider.lower(),
        metric=data.metric,
        threshold=data.threshold,
        enabled=data.enabled,
    )
    db.add(rule)
    await db.flush()
    return AlertConfigOut(
        id=rule.id,
        provider=rule.provider,
        metric=rule.metric,
        threshold=rule.threshold,
        enabled=rule.enabled,
    )


@router.delete("/config/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_alert_config(id: int, db: AsyncSession = Depends(get_db)):
    """Delete an alert configuration rule."""
    stmt = select(AlertConfig).where(AlertConfig.id == id)
    rule = (await db.execute(stmt)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Regra de alerta não encontrada")
    await db.delete(rule)
