"""
routers/fallback_rules.py — CRUD endpoints for model failover and fallback rules.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import FallbackRule
from security import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fallback-rules", tags=["fallback-rules"])


class FallbackRuleIn(BaseModel):
    source_provider: str = Field(..., min_length=1, max_length=64)
    source_model: str = Field(..., min_length=1, max_length=128)
    target_provider: str = Field(..., min_length=1, max_length=64)
    target_model: str = Field(..., min_length=1, max_length=128)
    priority: int = Field(default=1, ge=1)
    enabled: bool = True


class FallbackRuleOut(BaseModel):
    id: int
    source_provider: str
    source_model: str
    target_provider: str
    target_model: str
    priority: int
    enabled: bool
    created_at: datetime


@router.get("", response_model=List[FallbackRuleOut])
async def list_fallback_rules(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(require_admin),
):
    """List all fallback rules ordered by source provider and priority."""
    stmt = select(FallbackRule).order_by(
        FallbackRule.source_provider,
        FallbackRule.source_model,
        FallbackRule.priority,
    )
    rules = (await db.execute(stmt)).scalars().all()
    return [
        FallbackRuleOut(
            id=r.id,
            source_provider=r.source_provider,
            source_model=r.source_model,
            target_provider=r.target_provider,
            target_model=r.target_model,
            priority=r.priority,
            enabled=r.enabled,
            created_at=r.created_at,
        )
        for r in rules
    ]


@router.post("", response_model=FallbackRuleOut, status_code=status.HTTP_201_CREATED)
async def create_fallback_rule(
    payload: FallbackRuleIn,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(require_admin),
):
    """Create a new model fallback rule."""
    rule = FallbackRule(
        source_provider=payload.source_provider.strip().lower(),
        source_model=payload.source_model.strip(),
        target_provider=payload.target_provider.strip().lower(),
        target_model=payload.target_model.strip(),
        priority=payload.priority,
        enabled=payload.enabled,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    logger.info("Created fallback rule: %s/%s -> %s/%s (priority %d)",
                rule.source_provider, rule.source_model, rule.target_provider, rule.target_model, rule.priority)
    return FallbackRuleOut(
        id=rule.id,
        source_provider=rule.source_provider,
        source_model=rule.source_model,
        target_provider=rule.target_provider,
        target_model=rule.target_model,
        priority=rule.priority,
        enabled=rule.enabled,
        created_at=rule.created_at,
    )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fallback_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(require_admin),
):
    """Delete a fallback rule by ID."""
    stmt = select(FallbackRule).where(FallbackRule.id == rule_id)
    rule = (await db.execute(stmt)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra de fallback não encontrada.")
    await db.delete(rule)
    await db.commit()
    logger.info("Deleted fallback rule #%d", rule_id)


@router.put("/{rule_id}/toggle", response_model=FallbackRuleOut)
async def toggle_fallback_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(require_admin),
):
    """Toggle a fallback rule enabled/disabled state."""
    stmt = select(FallbackRule).where(FallbackRule.id == rule_id)
    rule = (await db.execute(stmt)).scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regra de fallback não encontrada.")
    rule.enabled = not rule.enabled
    await db.commit()
    await db.refresh(rule)
    logger.info("Toggled fallback rule #%d to enabled=%s", rule_id, rule.enabled)
    return FallbackRuleOut(
        id=rule.id,
        source_provider=rule.source_provider,
        source_model=rule.source_model,
        target_provider=rule.target_provider,
        target_model=rule.target_model,
        priority=rule.priority,
        enabled=rule.enabled,
        created_at=rule.created_at,
    )
