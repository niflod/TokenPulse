"""
routers/api_keys.py — CRUD endpoints for TokenPulse Virtual Client API Keys.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import ClientApiKey
from security import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["client_keys"])


class ClientKeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    rate_limit_rpm: Optional[int] = Field(60, ge=1, le=10000)


class ClientKeyOut(BaseModel):
    id: int
    name: str
    key_prefix: str
    rate_limit_rpm: Optional[int]
    enabled: bool
    created_at: str
    last_used_at: Optional[str] = None


class ClientKeyCreatedResponse(ClientKeyOut):
    api_key: str  # Only returned upon creation


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


@router.get("", response_model=List[ClientKeyOut], dependencies=[Depends(require_admin)])
async def list_client_keys(db: AsyncSession = Depends(get_db)):
    """List all issued client API keys."""
    stmt = select(ClientApiKey).order_by(ClientApiKey.id.desc())
    keys = (await db.execute(stmt)).scalars().all()
    return [
        ClientKeyOut(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            rate_limit_rpm=k.rate_limit_rpm,
            enabled=k.enabled,
            created_at=k.created_at.isoformat(),
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        )
        for k in keys
    ]


@router.post(
    "",
    response_model=ClientKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_client_key(
    data: ClientKeyCreateIn, db: AsyncSession = Depends(get_db)
):
    """Generate and issue a new client API key."""
    raw_random = secrets.token_hex(20)
    raw_key = f"tp_live_{raw_random}"
    prefix = f"tp_live_{raw_random[:4]}..."
    k_hash = hash_key(raw_key)

    record = ClientApiKey(
        name=data.name.strip(),
        key_prefix=prefix,
        key_hash=k_hash,
        rate_limit_rpm=data.rate_limit_rpm,
        enabled=True,
    )
    db.add(record)
    await db.flush()

    return ClientKeyCreatedResponse(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        rate_limit_rpm=record.rate_limit_rpm,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        last_used_at=None,
        api_key=raw_key,
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def revoke_client_key(id: int, db: AsyncSession = Depends(get_db)):
    """Revoke and delete a client API key."""
    stmt = select(ClientApiKey).where(ClientApiKey.id == id)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Chave de cliente não encontrada.")
    await db.delete(record)


@router.put("/{id}/toggle", response_model=ClientKeyOut, dependencies=[Depends(require_admin)])
async def toggle_client_key(id: int, db: AsyncSession = Depends(get_db)):
    """Enable or disable a client API key."""
    stmt = select(ClientApiKey).where(ClientApiKey.id == id)
    record = (await db.execute(stmt)).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Chave de cliente não encontrada.")
    record.enabled = not record.enabled
    await db.flush()
    return ClientKeyOut(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        rate_limit_rpm=record.rate_limit_rpm,
        enabled=record.enabled,
        created_at=record.created_at.isoformat(),
        last_used_at=record.last_used_at.isoformat() if record.last_used_at else None,
    )
