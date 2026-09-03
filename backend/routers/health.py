"""
routers/health.py — Health check endpoint probing provider APIs.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import ProviderConfig
from services.aggregator import aggregator

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def get_health_status(db: AsyncSession = Depends(get_db)):
    """
    Check connection status and latency for all registered and configured providers.
    Never fails the whole endpoint if a single provider is offline.
    """
    stmt = select(ProviderConfig).where(ProviderConfig.enabled == True)
    providers = (await db.execute(stmt)).scalars().all()

    results = []
    tasks = []
    p_names = []

    # Ensure all enabled providers are in aggregator
    for p in providers:
        p_name = p.name.lower()
        adapter = aggregator.get_adapter(p_name)
        if adapter:
            tasks.append(adapter.get_health())
            p_names.append(p_name)
        else:
            results.append({
                "provider": p_name,
                "displayName": p.display_name,
                "status": "UNKNOWN",
                "latency_ms": None,
                "last_check": datetime.now(timezone.utc).isoformat(),
                "details": {"reason": "Adaptador não inicializado ou sem chave"},
            })

    if tasks:
        health_results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, res in zip(p_names, health_results):
            disp = next((p.display_name for p in providers if p.name.lower() == name), name)
            if isinstance(res, Exception):
                results.append({
                    "provider": name,
                    "displayName": disp,
                    "status": "UNKNOWN",
                    "latency_ms": None,
                    "last_check": datetime.now(timezone.utc).isoformat(),
                    "details": {"reason": str(res)},
                })
            else:
                results.append({
                    "provider": res.provider,
                    "displayName": disp,
                    "status": res.status,
                    "latency_ms": res.latency_ms,
                    "last_check": res.last_check,
                    "details": res.details,
                })

    # If no providers configured at all, return default known providers as UNKNOWN
    if not results:
        known = [
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic"),
            ("gemini", "Google Gemini"),
        ]
        now_iso = datetime.now(timezone.utc).isoformat()
        for k_id, k_name in known:
            results.append({
                "provider": k_id,
                "displayName": k_name,
                "status": "UNKNOWN",
                "latency_ms": None,
                "last_check": now_iso,
                "details": {"reason": "Nenhuma credencial configurada"},
            })

    return results
