"""
routers/cache_router.py — Gateway Response Cache Management API.
Exposes statistics on cost savings, cache flush, and runtime TTL/toggle configuration.
"""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import RequestLog
from security import require_admin
from services.cache_service import flush_all_cache, get_cache_statistics

router = APIRouter(prefix="/api/cache", tags=["cache"])


class CacheConfigUpdate(BaseModel):
    enabled: Optional[bool] = Field(None, description="Toggle gateway response caching globally")
    default_ttl: Optional[int] = Field(None, ge=1, le=2592000, description="Default TTL in seconds")


@router.get("/stats")
async def get_cache_stats(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Retrieves cache performance and cumulative financial savings."""
    stats = await get_cache_statistics(db)

    # Calculate overall cache hit rate from RequestLog
    total_reqs = (await db.execute(select(func.count(RequestLog.id)))).scalar() or 0
    cache_hits = (
        await db.execute(
            select(func.count(RequestLog.id)).where(RequestLog.cache_hit == True)
        )
    ).scalar() or 0

    hit_rate = round((cache_hits / total_reqs * 100), 1) if total_reqs > 0 else 0.0

    return {
        "active_entries": stats["active_entries"],
        "total_hits": stats["total_hits"],
        "total_saved_cost_usd": stats["total_saved_cost_usd"],
        "cache_hit_rate_pct": hit_rate,
        "total_gateway_requests": total_reqs,
        "total_cached_requests": cache_hits,
        "enabled": settings.gateway_cache_enabled,
        "default_ttl_seconds": settings.gateway_cache_default_ttl,
    }


@router.get("/config")
async def get_cache_config(
    admin: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Returns current gateway caching runtime configuration."""
    return {
        "enabled": settings.gateway_cache_enabled,
        "default_ttl_seconds": settings.gateway_cache_default_ttl,
    }


@router.put("/config")
async def update_cache_config(
    data: CacheConfigUpdate,
    admin: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Updates runtime gateway caching configuration."""
    if data.enabled is not None:
        settings.gateway_cache_enabled = data.enabled
    if data.default_ttl is not None:
        settings.gateway_cache_default_ttl = data.default_ttl

    return {
        "status": "ok",
        "enabled": settings.gateway_cache_enabled,
        "default_ttl_seconds": settings.gateway_cache_default_ttl,
    }


@router.post("/flush")
async def flush_cache(
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Invalidates and deletes all stored response cache entries."""
    deleted_count = await flush_all_cache(db)
    return {
        "status": "ok",
        "message": f"Cache esvaziado com sucesso. {deleted_count} entradas removidas.",
        "deleted_entries": deleted_count,
    }
