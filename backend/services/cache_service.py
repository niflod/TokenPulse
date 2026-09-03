"""
services/cache_service.py — Deterministic hashing, SQLite caching and eviction for Gateway.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import GatewayResponseCache, RequestLog


def compute_gateway_cache_key(
    provider: str,
    model: str,
    body_json: Dict[str, Any],
    subpath: Optional[str] = None,
) -> str:
    """
    Computes a deterministic SHA-256 hash for gateway caching.
    Extracts semantic parameters (provider, model, subpath, messages, temperature, tools)
    and excludes non-semantic/transient flags like stream and user.
    """
    clean_provider = provider.lower().strip()
    clean_model = model.strip()

    semantic_payload = {
        "provider": clean_provider,
        "model": clean_model,
        "subpath": subpath.strip("/") if subpath else "",
        "messages": body_json.get("messages") or body_json.get("prompt"),
        "temperature": round(float(body_json.get("temperature", 1.0)), 3) if body_json.get("temperature") is not None else 1.0,
        "top_p": round(float(body_json.get("top_p", 1.0)), 3) if body_json.get("top_p") is not None else 1.0,
        "tools": body_json.get("tools"),
        "tool_choice": body_json.get("tool_choice"),
        "response_format": body_json.get("response_format"),
    }
    canonical_json = json.dumps(semantic_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


async def evict_expired_cache(db: AsyncSession) -> int:
    """Deletes all cache entries where expires_at <= current UTC time."""
    now = datetime.now(timezone.utc)
    stmt = (
        delete(GatewayResponseCache)
        .where(GatewayResponseCache.expires_at <= now)
        .execution_options(synchronize_session=False)
    )
    res = await db.execute(stmt)
    await db.commit()
    return res.rowcount


async def get_cached_response(
    db: AsyncSession, cache_key: str
) -> Optional[GatewayResponseCache]:
    """
    Retrieves a valid, unexpired cached response. Increments hit_count on HIT.
    Returns None if missing or expired.
    """
    now = datetime.now(timezone.utc)
    stmt = select(GatewayResponseCache).where(
        GatewayResponseCache.cache_key == cache_key,
        GatewayResponseCache.expires_at > now,
    )
    entry = (await db.execute(stmt)).scalar_one_or_none()
    if entry:
        entry.hit_count += 1
        await db.commit()
        return entry
    return None


async def set_cached_response(
    db: AsyncSession,
    cache_key: str,
    provider: str,
    model: str,
    response_json: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    estimated_saved_cost: Optional[float] = None,
    ttl_seconds: int = 3600,
) -> GatewayResponseCache:
    """Stores or updates a cached response with specified TTL."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(ttl_seconds, 1))

    existing = (
        await db.execute(
            select(GatewayResponseCache).where(GatewayResponseCache.cache_key == cache_key)
        )
    ).scalar_one_or_none()

    if existing:
        existing.provider = provider.lower().strip()
        existing.model = model.strip()
        existing.response_json = response_json
        existing.input_tokens = input_tokens
        existing.output_tokens = output_tokens
        existing.total_tokens = total_tokens
        existing.estimated_saved_cost = estimated_saved_cost
        existing.expires_at = expires
        await db.commit()
        return existing

    new_entry = GatewayResponseCache(
        cache_key=cache_key,
        provider=provider.lower().strip(),
        model=model.strip(),
        response_json=response_json,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_saved_cost=estimated_saved_cost,
        hit_count=0,
        created_at=now,
        expires_at=expires,
    )
    db.add(new_entry)
    await db.commit()
    return new_entry


async def flush_all_cache(db: AsyncSession) -> int:
    """Deletes all cache entries and returns count of removed items."""
    count_stmt = select(func.count(GatewayResponseCache.cache_key))
    total_count = (await db.execute(count_stmt)).scalar() or 0
    await db.execute(delete(GatewayResponseCache))
    await db.commit()
    return total_count


async def get_cache_statistics(db: AsyncSession) -> Dict[str, Any]:
    """Calculates statistics: active entries, total hits, total saved dollars and hit rate."""
    await evict_expired_cache(db)
    now = datetime.now(timezone.utc)

    active_count = (
        await db.execute(
            select(func.count(GatewayResponseCache.cache_key)).where(
                GatewayResponseCache.expires_at > now
            )
        )
    ).scalar() or 0

    total_hits = (
        await db.execute(select(func.sum(GatewayResponseCache.hit_count)))
    ).scalar() or 0

    total_saved_cost = (
        await db.execute(
            select(func.sum(GatewayResponseCache.estimated_saved_cost * GatewayResponseCache.hit_count))
        )
    ).scalar() or 0.0

    total_reqs = (await db.execute(select(func.count(RequestLog.id)))).scalar() or 0
    cached_reqs = (
        await db.execute(
            select(func.count(RequestLog.id)).where(RequestLog.cache_hit == True)
        )
    ).scalar() or 0
    total_misses = max(total_reqs - cached_reqs, 0)
    hit_rate = round((cached_reqs / total_reqs * 100), 1) if total_reqs > 0 else 0.0

    return {
        "active_entries": active_count,
        "total_hits": int(total_hits),
        "total_misses": int(total_misses),
        "total_saved_cost_usd": round(float(total_saved_cost), 4),
        "total_gateway_requests": total_reqs,
        "total_cached_requests": cached_reqs,
        "cache_hit_rate_pct": hit_rate,
    }
