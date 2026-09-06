"""
routers/sync.py — Usage synchronization endpoints.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import User
from routers.auth import get_current_user
from services.usage_sync import sync_user_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


class SyncRequest(BaseModel):
    provider: Optional[str] = None


@router.post("/now")
async def trigger_sync_now(
    data: Optional[SyncRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an immediate usage synchronization for the authenticated user."""
    provider_name = data.provider if data else None
    return await sync_user_providers(db, user_id=current_user.id, provider_name=provider_name)
