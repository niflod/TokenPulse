"""
routers/providers.py — CRUD endpoints for provider configurations.
"""

from __future__ import annotations

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import ProviderConfig
from security import require_admin, validate_provider_base_url
from services.aggregator import aggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])

SupportedProvider = Literal["openai", "anthropic", "gemini", "groq", "mistral", "ollama"]


class ProviderCreateRequest(BaseModel):
    name: SupportedProvider
    display_name: str = Field(..., min_length=1, max_length=128)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    enabled: bool = True


class ProviderResponse(BaseModel):
    id: int
    name: str
    display_name: str
    base_url: Optional[str] = None
    enabled: bool
    has_api_key: bool
    masked_key: Optional[str] = None


@router.get("", response_model=List[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    """List configured providers without exposing decrypted secrets."""
    stmt = select(ProviderConfig).order_by(ProviderConfig.name)
    result = await db.execute(stmt)
    providers = result.scalars().all()

    return [
        ProviderResponse(
            id=p.id,
            name=p.name,
            display_name=p.display_name,
            base_url=p.base_url,
            enabled=p.enabled,
            has_api_key=bool(p.api_key_encrypted),
            masked_key="••••••••" if p.api_key_encrypted else None,
        )
        for p in providers
    ]


@router.post("", response_model=ProviderResponse, dependencies=[Depends(require_admin)])
async def upsert_provider(
    data: ProviderCreateRequest, db: AsyncSession = Depends(get_db)
):
    """Create or update a provider config, validating SSRF and encrypting the API key."""
    clean_name = data.name.lower().strip()
    validated_url = validate_provider_base_url(clean_name, data.base_url)

    stmt = select(ProviderConfig).where(ProviderConfig.name == clean_name)
    existing = (await db.execute(stmt)).scalar_one_or_none()

    secret = settings.get_fernet_key()

    if existing:
        existing.display_name = data.display_name
        existing.base_url = validated_url
        existing.enabled = data.enabled
        if data.api_key:
            existing.api_key_encrypted = ProviderConfig.encrypt_key(data.api_key, secret)
        await db.flush()
        target = existing
    else:
        enc_key = None
        if data.api_key:
            enc_key = ProviderConfig.encrypt_key(data.api_key, secret)
        target = ProviderConfig(
            name=clean_name,
            display_name=data.display_name,
            api_key_encrypted=enc_key,
            base_url=validated_url,
            enabled=data.enabled,
        )
        db.add(target)
        await db.flush()

    # Register/Update in aggregator
    raw_key = data.api_key
    if not raw_key and target.api_key_encrypted:
        raw_key = target.decrypt_key(secret)

    if target.enabled:
        aggregator.register_provider(target.name, api_key=raw_key, base_url=target.base_url)
    else:
        aggregator.unregister_provider(target.name)

    return ProviderResponse(
        id=target.id,
        name=target.name,
        display_name=target.display_name,
        base_url=target.base_url,
        enabled=target.enabled,
        has_api_key=bool(target.api_key_encrypted),
        masked_key="••••••••" if target.api_key_encrypted else None,
    )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
async def delete_provider(name: str, db: AsyncSession = Depends(get_db)):
    """Delete a provider configuration."""
    clean_name = name.lower().strip()
    stmt = select(ProviderConfig).where(ProviderConfig.name == clean_name)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Provedor não encontrado")

    await db.delete(existing)
    aggregator.unregister_provider(clean_name)


@router.put("/{name}/toggle", response_model=ProviderResponse, dependencies=[Depends(require_admin)])
async def toggle_provider(name: str, db: AsyncSession = Depends(get_db)):
    """Toggle enabled status of a provider."""
    clean_name = name.lower().strip()
    stmt = select(ProviderConfig).where(ProviderConfig.name == clean_name)
    provider = (await db.execute(stmt)).scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provedor não encontrado")

    provider.enabled = not provider.enabled
    await db.flush()

    secret = settings.get_fernet_key()
    if provider.enabled:
        raw_key = provider.decrypt_key(secret)
        aggregator.register_provider(provider.name, api_key=raw_key, base_url=provider.base_url)
    else:
        aggregator.unregister_provider(provider.name)

    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        display_name=provider.display_name,
        base_url=provider.base_url,
        enabled=provider.enabled,
        has_api_key=bool(provider.api_key_encrypted),
        masked_key="••••••••" if provider.api_key_encrypted else None,
    )
