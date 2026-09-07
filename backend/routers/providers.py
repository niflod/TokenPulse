"""
routers/providers.py — CRUD endpoints for provider configurations.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models import ProviderConfig, User
from routers.auth import get_current_user
from security import require_admin, validate_provider_base_url
from services.aggregator import aggregator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])

SupportedProvider = Literal["openai", "anthropic", "gemini", "groq", "mistral", "ollama", "openrouter"]


class ProviderCreateRequest(BaseModel):
    name: SupportedProvider
    display_name: str = Field(..., min_length=1, max_length=128)
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    enabled: bool = True


class ProviderValidateRequest(BaseModel):
    name: SupportedProvider
    api_key: str = Field(..., min_length=1)
    base_url: Optional[str] = None


class ProviderValidateResponse(BaseModel):
    valid: bool
    message: str
    details: Optional[dict] = None


class ProviderResponse(BaseModel):
    id: int
    name: str
    display_name: str
    base_url: Optional[str] = None
    enabled: bool
    has_api_key: bool
    masked_key: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    sync_status: Optional[str] = "idle"
    sync_error: Optional[str] = None


@router.post("/validate", response_model=ProviderValidateResponse)
async def validate_provider(
    data: ProviderValidateRequest,
    user: Optional[User] = Depends(get_current_user),
):
    """Test API key credentials against official provider endpoint without saving."""
    import httpx
    clean_name = data.name.lower().strip()
    clean_key = data.api_key.strip()
    validated_url = validate_provider_base_url(clean_name, data.base_url)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if clean_name == "openai":
                url = (validated_url or "https://api.openai.com/v1").rstrip("/") + "/models"
                res = await client.get(url, headers={"Authorization": f"Bearer {clean_key}"})
            elif clean_name == "openrouter":
                url = (validated_url or "https://openrouter.ai/api/v1").rstrip("/") + "/auth/key"
                res = await client.get(url, headers={"Authorization": f"Bearer {clean_key}"})
            elif clean_name == "anthropic":
                url = (validated_url or "https://api.anthropic.com/v1").rstrip("/") + "/models"
                res = await client.get(url, headers={"x-api-key": clean_key, "anthropic-version": "2023-06-01"})
            elif clean_name == "gemini":
                url = (validated_url or "https://generativelanguage.googleapis.com").rstrip("/") + "/v1beta/models"
                res = await client.get(url, headers={"x-goog-api-key": clean_key})
            elif clean_name == "groq":
                url = (validated_url or "https://api.groq.com/openai/v1").rstrip("/") + "/models"
                res = await client.get(url, headers={"Authorization": f"Bearer {clean_key}"})
            elif clean_name == "mistral":
                url = (validated_url or "https://api.mistral.ai/v1").rstrip("/") + "/models"
                res = await client.get(url, headers={"Authorization": f"Bearer {clean_key}"})
            elif clean_name == "ollama":
                url = (validated_url or "http://localhost:11434").rstrip("/") + "/api/tags"
                res = await client.get(url)
            else:
                return ProviderValidateResponse(valid=False, message=f"Provedor '{clean_name}' não suporta validação automática.")

        if res.status_code in (200, 201):
            return ProviderValidateResponse(
                valid=True,
                message="Credencial verificada com sucesso!",
                details={"status_code": res.status_code},
            )
        elif res.status_code in (401, 403):
            return ProviderValidateResponse(
                valid=False,
                message=f"Chave de API inválida ou sem permissão (HTTP {res.status_code}).",
                details={"status_code": res.status_code},
            )
        else:
            return ProviderValidateResponse(
                valid=False,
                message=f"Resposta inesperada do provedor (HTTP {res.status_code}).",
                details={"status_code": res.status_code},
            )
    except httpx.TimeoutException:
        return ProviderValidateResponse(
            valid=False,
            message="Tempo limite esgotado ao contatar o provedor.",
        )
    except Exception as exc:
        logger.warning("Erro validando provedor %s: %s", clean_name, exc)
        return ProviderValidateResponse(
            valid=False,
            message=f"Erro de conexão com o provedor: {str(exc)}",
        )


@router.get("", response_model=List[ProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """List configured providers for the authenticated user without exposing decrypted secrets."""
    from sqlalchemy import or_
    stmt = select(ProviderConfig)
    if user and user.id:
        stmt = stmt.where(or_(ProviderConfig.user_id == user.id, ProviderConfig.user_id.is_(None)))
    stmt = stmt.order_by(ProviderConfig.name)
    result = await db.execute(stmt)
    providers = result.scalars().all()

    secret = settings.get_fernet_key()
    res = []
    for p in providers:
        masked = None
        if p.api_key_encrypted:
            try:
                dec = p.decrypt_key(secret)
                masked = f"{dec[:4]}...{dec[-4:]}" if len(dec) >= 8 else "••••••••"
            except Exception:
                masked = "••••••••"

        res.append(
            ProviderResponse(
                id=p.id,
                name=p.name,
                display_name=p.display_name,
                base_url=p.base_url,
                enabled=p.enabled,
                has_api_key=bool(p.api_key_encrypted),
                masked_key=masked,
                last_synced_at=p.last_synced_at,
                sync_status=p.sync_status or "idle",
                sync_error=p.sync_error,
            )
        )
    return res


@router.post("", response_model=ProviderResponse)
async def upsert_provider(
    data: ProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Create or update a provider config, validating SSRF and encrypting the API key."""
    from sqlalchemy import or_
    clean_name = data.name.lower().strip()
    validated_url = validate_provider_base_url(clean_name, data.base_url)

    uid = user.id if user else None
    stmt = select(ProviderConfig).where(ProviderConfig.name == clean_name)
    if uid:
        stmt = stmt.where(ProviderConfig.user_id == uid)
    else:
        stmt = stmt.where(ProviderConfig.user_id.is_(None))

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
            user_id=uid,
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
        aggregator.register_provider(target.name, api_key=raw_key, base_url=target.base_url, user_id=target.user_id)
    else:
        aggregator.unregister_provider(target.name, user_id=target.user_id)

    return ProviderResponse(
        id=target.id,
        name=target.name,
        display_name=target.display_name,
        base_url=target.base_url,
        enabled=target.enabled,
        has_api_key=bool(target.api_key_encrypted),
        masked_key="••••••••" if target.api_key_encrypted else None,
        last_synced_at=target.last_synced_at,
        sync_status=target.sync_status or "idle",
        sync_error=target.sync_error,
    )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Delete a provider configuration."""
    clean_name = name.lower().strip()
    uid = user.id if user else None
    stmt = select(ProviderConfig).where(ProviderConfig.name == clean_name)
    if uid:
        stmt = stmt.where(ProviderConfig.user_id == uid)
    else:
        stmt = stmt.where(ProviderConfig.user_id.is_(None))
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if not existing:
        raise HTTPException(status_code=404, detail="Provedor não encontrado")

    await db.delete(existing)
    aggregator.unregister_provider(clean_name, user_id=existing.user_id)


@router.put("/{name}/toggle", response_model=ProviderResponse)
async def toggle_provider(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_current_user),
):
    """Toggle enabled status of a provider."""
    clean_name = name.lower().strip()
    uid = user.id if user else None
    stmt = select(ProviderConfig).where(ProviderConfig.name == clean_name)
    if uid:
        stmt = stmt.where(ProviderConfig.user_id == uid)
    else:
        stmt = stmt.where(ProviderConfig.user_id.is_(None))
    provider = (await db.execute(stmt)).scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provedor não encontrado")

    provider.enabled = not provider.enabled
    await db.flush()

    secret = settings.get_fernet_key()
    if provider.enabled:
        raw_key = provider.decrypt_key(secret)
        aggregator.register_provider(provider.name, api_key=raw_key, base_url=provider.base_url, user_id=provider.user_id)
    else:
        aggregator.unregister_provider(provider.name, user_id=provider.user_id)

    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        display_name=provider.display_name,
        base_url=provider.base_url,
        enabled=provider.enabled,
        has_api_key=bool(provider.api_key_encrypted),
        masked_key="••••••••" if provider.api_key_encrypted else None,
        last_synced_at=provider.last_synced_at,
        sync_status=provider.sync_status or "idle",
        sync_error=provider.sync_error,
    )
