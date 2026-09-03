"""
routers/gateway.py — TokenPulse Transparent AI Gateway & Telemetry Ingestion.
Enables clients to point their base_url to TokenPulse for automatic observability,
measuring latency, TTFT, token usage, cost, and streaming chunks.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Literal, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal, get_db
from models import ProviderConfig, RequestLog
from pricing import lookup_pricing
from security import (
    OFFICIAL_PROVIDER_DOMAINS,
    gateway_rate_limiter,
    redact_sensitive_text,
    require_admin,
    validate_provider_base_url,
)
from services.cache_service import (
    compute_gateway_cache_key,
    get_cached_response,
    set_cached_response,
)
from services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gateway"])

SupportedProvider = Literal["openai", "anthropic", "gemini", "groq", "mistral", "ollama"]

DEFAULT_UPSTREAM_BASES: Dict[str, str] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
    "groq": "https://api.groq.com/openai",
    "mistral": "https://api.mistral.ai",
    "ollama": "http://127.0.0.1:11434",
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


# -----------------------------------------------------------------------------
# Telemetry Ingestion (Existing Endpoint — PRESERVED & EXTENDED)
# -----------------------------------------------------------------------------

class TelemetryEvent(BaseModel):
    provider: SupportedProvider
    model: str = Field(..., min_length=1, max_length=128)
    input_tokens: Optional[int] = Field(None, ge=0)
    output_tokens: Optional[int] = Field(None, ge=0)
    total_tokens: Optional[int] = Field(None, ge=0)
    latency_ms: Optional[float] = Field(None, ge=0.0)
    status_code: Optional[int] = Field(200, ge=100, le=599)
    error_message: Optional[str] = None
    request_id: Optional[str] = Field(None, max_length=256)
    timestamp: Optional[datetime] = None


@router.post("/api/v1/telemetry", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
async def ingest_telemetry(data: TelemetryEvent, db: AsyncSession = Depends(get_db)):
    """
    Direct ingestion for external TokenPulse SDKs and manual telemetry calls.
    """
    tot_tok = data.total_tokens
    if tot_tok is None and data.input_tokens is not None and data.output_tokens is not None:
        tot_tok = data.input_tokens + data.output_tokens

    inp_price, out_price, _, _ = lookup_pricing(data.provider, data.model)
    cost_in = None
    cost_out = None
    cost_tot = None

    if inp_price is not None and data.input_tokens is not None:
        cost_in = (data.input_tokens / 1_000_000) * inp_price
    if out_price is not None and data.output_tokens is not None:
        cost_out = (data.output_tokens / 1_000_000) * out_price
    if cost_in is not None or cost_out is not None:
        cost_tot = round((cost_in or 0.0) + (cost_out or 0.0), 6)

    event_time = data.timestamp or datetime.now(timezone.utc)
    req_id = data.request_id or f"tp_req_{uuid.uuid4().hex[:16]}"

    log_entry = RequestLog(
        provider=data.provider.lower(),
        model=data.model,
        timestamp=event_time,
        input_tokens=data.input_tokens,
        output_tokens=data.output_tokens,
        total_tokens=tot_tok,
        latency_ms=data.latency_ms,
        status_code=data.status_code,
        error_message=redact_sensitive_text(data.error_message),
        cost_input=round(cost_in, 6) if cost_in is not None else None,
        cost_output=round(cost_out, 6) if cost_out is not None else None,
        cost_total=cost_tot,
        request_id=req_id,
    )

    db.add(log_entry)
    await db.flush()

    # Publish real-time event to dashboard
    await event_bus.publish("request.completed", {
        "request_id": req_id,
        "provider": data.provider.lower(),
        "model": data.model,
        "tokens": tot_tok,
        "cost": cost_tot,
        "latency_ms": data.latency_ms,
        "status": data.status_code,
    })

    return {
        "status": "ingested",
        "log_id": log_entry.id,
        "request_id": req_id,
        "estimated_cost_usd": cost_tot,
    }


async def _is_provider_budget_exceeded(provider: str) -> tuple[bool, float, float]:
    """Returns (exceeded, total_spent, budget)."""
    budget = getattr(settings, "provider_monthly_budget", None)
    if not budget or budget <= 0:
        return False, 0.0, 0.0

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    async with AsyncSessionLocal() as db:
        q = select(func.sum(RequestLog.cost_total)).where(
            RequestLog.provider == provider.lower(),
            RequestLog.timestamp >= month_start,
        )
        total_spent = (await db.execute(q)).scalar() or 0.0
        return total_spent >= budget, total_spent, budget


async def _get_fallback_targets(source_provider: str, source_model: str) -> list[tuple[str, str]]:
    """Returns list of (target_provider, target_model) ordered by priority."""
    from models import FallbackRule
    async with AsyncSessionLocal() as db:
        stmt = select(FallbackRule).where(
            FallbackRule.source_provider == source_provider.lower(),
            FallbackRule.enabled == True,
        ).order_by(FallbackRule.priority)
        rules = (await db.execute(stmt)).scalars().all()
        targets: list[tuple[str, str]] = []
        for r in rules:
            if r.source_model == source_model or r.source_model == "*":
                pair = (r.target_provider.lower().strip(), r.target_model.strip())
                if pair not in targets:
                    targets.append(pair)
        return targets


async def _resolve_provider_credentials(provider: str, client_auth_header: Optional[str]) -> tuple[Optional[str], str]:
    """
    Resolves the upstream API key and base URL.
    Uses incoming client key if provided, otherwise decrypts the key configured in DB.
    """
    clean_provider = provider.lower().strip()
    configured_base = DEFAULT_UPSTREAM_BASES.get(clean_provider, "https://api.openai.com")
    resolved_key = None

    # 1. Check if client sent an Authorization / API key header
    is_virtual_key = False
    if client_auth_header and client_auth_header.strip():
        parts = client_auth_header.strip().split()
        candidate = parts[-1] if len(parts) > 1 else parts[0]
        if candidate and candidate.startswith("tp_live_"):
            is_virtual_key = True
            import hashlib
            from models import ClientApiKey
            k_hash = hashlib.sha256(candidate.strip().encode("utf-8")).hexdigest()
            async with AsyncSessionLocal() as db:
                stmt = select(ClientApiKey).where(ClientApiKey.key_hash == k_hash, ClientApiKey.enabled == True)
                k_rec = (await db.execute(stmt)).scalar_one_or_none()
                if not k_rec:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Chave virtual TokenPulse (tp_live_...) inválida ou desabilitada.",
                    )
                k_rec.last_used_at = datetime.now(timezone.utc)
                await db.commit()
            resolved_key = None  # Will resolve from DB provider configuration below
        elif candidate and not candidate.startswith("tp_dummy_"):
            resolved_key = candidate

    # 2. If not provided by client, retrieve from database
    async with AsyncSessionLocal() as db:
        stmt = select(ProviderConfig).where(ProviderConfig.name == clean_provider, ProviderConfig.enabled == True)
        res = await db.execute(stmt)
        p_cfg = res.scalar_one_or_none()
        if p_cfg:
            if not resolved_key and p_cfg.api_key_encrypted:
                secret = settings.get_fernet_key()
                resolved_key = p_cfg.decrypt_key(secret)
            if p_cfg.base_url:
                validated = validate_provider_base_url(clean_provider, p_cfg.base_url)
                if validated:
                    configured_base = validated

    # 3. Fallback to pre-configured environment variables
    if not resolved_key:
        if clean_provider == "openai":
            resolved_key = settings.openai_api_key
        elif clean_provider == "anthropic":
            resolved_key = settings.anthropic_api_key
        elif clean_provider == "gemini":
            resolved_key = settings.gemini_api_key
        elif clean_provider == "groq":
            resolved_key = settings.groq_api_key
        elif clean_provider == "mistral":
            resolved_key = settings.mistral_api_key
        elif clean_provider == "ollama":
            resolved_key = "ollama-local"

    if is_virtual_key and not resolved_key and clean_provider != "ollama":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Provedor upstream '{clean_provider}' não possui chave de API configurada no TokenPulse.",
        )

    return resolved_key, configured_base


def _calculate_cost(provider: str, model: str, input_tokens: Optional[int], output_tokens: Optional[int]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    inp_price, out_price, _, _ = lookup_pricing(provider, model)
    c_in, c_out, c_tot = None, None, None
    if inp_price is not None and input_tokens is not None:
        c_in = round((input_tokens / 1_000_000) * inp_price, 6)
    if out_price is not None and output_tokens is not None:
        c_out = round((output_tokens / 1_000_000) * out_price, 6)
    if c_in is not None or c_out is not None:
        c_tot = round((c_in or 0.0) + (c_out or 0.0), 6)
    return c_in, c_out, c_tot


async def _persist_gateway_telemetry(
    provider: str,
    model: str,
    status_code: int,
    latency_ms: float,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: Optional[int],
    cached_tokens: Optional[int],
    reasoning_tokens: Optional[int],
    ttft_ms: Optional[float],
    stream_duration_ms: Optional[float],
    finish_reason: Optional[str],
    provider_request_id: Optional[str],
    tokenpulse_request_id: str,
    error_msg: Optional[str] = None,
    fallback_triggered: bool = False,
    original_provider: Optional[str] = None,
    original_model: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    cache_hit: bool = False,
) -> None:
    """Saves telemetry asynchronously and emits event bus notification."""
    if not settings.telemetry_enabled:
        return

    if cache_hit:
        c_in, c_out, c_tot = 0.0, 0.0, 0.0
    else:
        c_in, c_out, c_tot = _calculate_cost(provider, model, input_tokens, output_tokens)

    try:
        async with AsyncSessionLocal() as db:
            log_entry = RequestLog(
                provider=provider.lower(),
                model=model or "unknown",
                timestamp=datetime.now(timezone.utc),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_ms=round(latency_ms, 2) if latency_ms else None,
                status_code=status_code,
                error_message=redact_sensitive_text(error_msg),
                cost_input=c_in,
                cost_output=c_out,
                cost_total=c_tot,
                request_id=tokenpulse_request_id,
                provider_request_id=provider_request_id,
                time_to_first_token_ms=round(ttft_ms, 2) if ttft_ms else None,
                stream_duration_ms=round(stream_duration_ms, 2) if stream_duration_ms else None,
                cached_input_tokens=cached_tokens,
                reasoning_tokens=reasoning_tokens,
                finish_reason=finish_reason,
                fallback_triggered=fallback_triggered,
                original_provider=original_provider,
                original_model=original_model,
                fallback_reason=fallback_reason,
                cache_hit=cache_hit,
            )
            db.add(log_entry)
            await db.commit()

        # Emit live real-time event
        event_name = "request.completed" if status_code < 400 else "request.failed"
        await event_bus.publish(event_name, {
            "request_id": tokenpulse_request_id,
            "provider": provider.lower(),
            "model": model,
            "tokens": total_tokens,
            "cost": c_tot,
            "latency_ms": round(latency_ms, 1),
            "ttft_ms": round(ttft_ms, 1) if ttft_ms else None,
            "status": status_code,
            "cache_hit": bool(cache_hit),
        })
    except Exception as e:
        logger.error("Failed to save gateway telemetry: %s", redact_sensitive_text(str(e)))


def _dispatch_cache_persistence(
    cache_key: str,
    provider: str,
    model: str,
    response_json: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: Optional[int],
    estimated_saved_cost: Optional[float],
    ttl_seconds: int,
) -> None:
    """Dispatches asynchronous cache insertion in background without blocking caller."""
    async def _save_task():
        try:
            async with AsyncSessionLocal() as cache_session:
                await set_cached_response(
                    db=cache_session,
                    cache_key=cache_key,
                    provider=provider,
                    model=model,
                    response_json=response_json,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_saved_cost=estimated_saved_cost,
                    ttl_seconds=ttl_seconds,
                )
        except Exception as err:
            logger.debug("Failed saving response cache: %s", err)

    asyncio.create_task(_save_task())


# -----------------------------------------------------------------------------
# Gateway Core Reverse Proxy Handler
# -----------------------------------------------------------------------------

async def _proxy_request(
    provider: str,
    subpath: str,
    request: Request,
) -> Response:
    """
    Transparent reverse proxy core forwarding requests to upstream AI providers.
    Supports regular and streaming responses, capturing full telemetry.
    """
    if not settings.gateway_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TokenPulse Gateway is currently disabled in configuration.",
        )

    clean_provider = provider.lower().strip()
    if clean_provider not in DEFAULT_UPSTREAM_BASES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provedor '{provider}' não suportado. Provedores válidos: openai, anthropic, gemini.",
        )

    # 1. Path traversal and injection defense
    if ".." in subpath or subpath.startswith("//") or "\\" in subpath:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Caminho de requisição inválido: sequências de path traversal são proibidas.",
        )

    # 2. Client Authentication & Virtual Key Validation
    client_ip = request.client.host if request.client else "127.0.0.1"
    client_auth = request.headers.get("authorization") or request.headers.get("x-api-key")
    auth_identity = client_ip

    if getattr(settings, "gateway_require_auth", True):
        if not client_auth or not client_auth.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Autenticação obrigatória no TokenPulse Gateway. Forneça uma chave virtual TokenPulse (tp_live_...) no header Authorization ou X-API-Key.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    if client_auth and client_auth.strip():
        parts = client_auth.strip().split()
        candidate = parts[-1] if len(parts) > 1 else parts[0]
        if candidate.startswith("tp_live_"):
            import hashlib
            from models import ClientApiKey
            k_hash = hashlib.sha256(candidate.strip().encode("utf-8")).hexdigest()
            async with AsyncSessionLocal() as db:
                stmt = select(ClientApiKey).where(ClientApiKey.key_hash == k_hash, ClientApiKey.enabled == True)
                k_rec = (await db.execute(stmt)).scalar_one_or_none()
                if not k_rec:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Chave virtual TokenPulse (tp_live_...) inválida ou desabilitada.",
                    )
                k_rec.last_used_at = datetime.now(timezone.utc)
                await db.commit()
            auth_identity = f"key_{k_hash[:16]}"
        elif candidate.startswith("tp_dummy_"):
            auth_identity = f"test_{candidate[:12]}"
        else:
            # BYOK key
            if not getattr(settings, "gateway_allow_byok", True):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Acesso BYOK (Bring Your Own Key) está desabilitado no Gateway. Utilize uma chave virtual TokenPulse (tp_live_...).",
                )
            import hashlib
            auth_identity = f"byok_{hashlib.sha256(candidate.encode('utf-8')).hexdigest()[:16]}"

    # 3. Rate Limiting Check (RPM por Identidade Autenticada / IP + Provider)
    client_key = f"{auth_identity}:{clean_provider}"
    allowed, retry_after = gateway_rate_limiter.is_allowed(client_key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de taxa de requisições excedido no TokenPulse Gateway. Tente novamente em instantes.",
            headers={"Retry-After": str(retry_after)},
        )

    # 4. Monthly Financial Budget Cap Check & Fallback Candidates Setup
    body = await request.body()
    if len(body) > settings.max_request_body_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload excede o tamanho máximo permitido de {settings.max_request_body_size} bytes.",
        )

    body_json: Dict[str, Any] = {}
    is_streaming = False
    model_name = "unknown"

    if body and "application/json" in request.headers.get("content-type", ""):
        try:
            body_json = json.loads(body.decode("utf-8"))
            is_streaming = bool(body_json.get("stream", False))
            model_name = str(body_json.get("model", "unknown"))
        except Exception:
            pass

    tp_req_id = f"tp_req_{uuid.uuid4().hex[:16]}"
    start_time = time.perf_counter()

    # 4. Response Caching Check (Deterministic SHA-256 Hash Matching)
    cache_header = request.headers.get("x-tokenpulse-cache", "").lower().strip()
    cache_control = request.headers.get("cache-control", "").lower().strip()
    is_cache_bypassed = (
        not settings.gateway_cache_enabled
        or request.method.upper() != "POST"
        or cache_header in ("false", "no-cache", "0", "off")
        or "no-cache" in cache_control
    )

    custom_ttl_header = request.headers.get("x-tokenpulse-cache-ttl")
    try:
        req_cache_ttl = int(custom_ttl_header) if custom_ttl_header else settings.gateway_cache_default_ttl
    except ValueError:
        req_cache_ttl = settings.gateway_cache_default_ttl

    cache_key = None
    if not is_cache_bypassed and body_json:
        cache_key = compute_gateway_cache_key(clean_provider, model_name, body_json, subpath=subpath)
        async with AsyncSessionLocal() as cache_db:
            cached_entry = await get_cached_response(cache_db, cache_key)
            if cached_entry:
                entry_created = cached_entry.created_at
                if entry_created.tzinfo is None:
                    entry_created = entry_created.replace(tzinfo=timezone.utc)
                cache_age = int((datetime.now(timezone.utc) - entry_created).total_seconds())
                resp_headers = {
                    "Content-Type": "application/json",
                    "X-TokenPulse-Request-Id": tp_req_id,
                    "X-TokenPulse-Cache": "HIT",
                    "X-TokenPulse-Cache-Age": str(max(cache_age, 0)),
                }

                if not is_streaming:
                    latency_ms = (time.perf_counter() - start_time) * 1000
                    asyncio.create_task(_persist_gateway_telemetry(
                        provider=clean_provider,
                        model=model_name,
                        status_code=200,
                        latency_ms=latency_ms,
                        input_tokens=cached_entry.input_tokens,
                        output_tokens=cached_entry.output_tokens,
                        total_tokens=cached_entry.total_tokens,
                        cached_tokens=None,
                        reasoning_tokens=None,
                        ttft_ms=None,
                        stream_duration_ms=None,
                        finish_reason="stop",
                        provider_request_id=f"cache_{cached_entry.cache_key[:12]}",
                        tokenpulse_request_id=tp_req_id,
                        cache_hit=True,
                    ))
                    return Response(
                        content=cached_entry.response_json.encode("utf-8"),
                        status_code=200,
                        headers=resp_headers,
                    )
                else:
                    # Streaming SSE Cache Hit: synthesize instant token stream
                    resp_headers["Content-Type"] = "text/event-stream"
                    resp_headers["Cache-Control"] = "no-cache"

                    async def cached_stream_generator() -> AsyncGenerator[bytes, None]:
                        ttft_recorded = (time.perf_counter() - start_time) * 1000
                        try:
                            try:
                                cached_data = json.loads(cached_entry.response_json)
                            except Exception:
                                cached_data = {}

                            content_text = ""
                            choices = cached_data.get("choices") or []
                            if choices and isinstance(choices, list) and isinstance(choices[0], dict):
                                content_text = choices[0].get("message", {}).get("content", "")
                            elif "content" in cached_data and isinstance(cached_data["content"], list) and len(cached_data["content"]) > 0:
                                content_text = cached_data["content"][0].get("text", "")

                            if clean_provider == "anthropic":
                                # Anthropic SSE format
                                init_chunk = {
                                    "type": "message_start",
                                    "message": {
                                        "id": f"msg-cache-{tp_req_id}",
                                        "type": "message",
                                        "role": "assistant",
                                        "content": [],
                                        "model": model_name,
                                        "stop_reason": None,
                                        "stop_sequence": None,
                                        "usage": {"input_tokens": cached_entry.input_tokens or 0, "output_tokens": cached_entry.output_tokens or 0},
                                    }
                                }
                                yield f"event: message_start\ndata: {json.dumps(init_chunk)}\n\n".encode("utf-8")

                                if content_text:
                                    content_block_start = {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
                                    yield f"event: content_block_start\ndata: {json.dumps(content_block_start)}\n\n".encode("utf-8")

                                    delta_chunk = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": content_text}}
                                    yield f"event: content_block_delta\ndata: {json.dumps(delta_chunk)}\n\n".encode("utf-8")

                                    content_block_stop = {"type": "content_block_stop", "index": 0}
                                    yield f"event: content_block_stop\ndata: {json.dumps(content_block_stop)}\n\n".encode("utf-8")

                                msg_delta = {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}}
                                yield f"event: message_delta\ndata: {json.dumps(msg_delta)}\n\n".encode("utf-8")

                                msg_stop = {"type": "message_stop"}
                                yield f"event: message_stop\ndata: {json.dumps(msg_stop)}\n\n".encode("utf-8")
                            else:
                                # OpenAI-compatible SSE format
                                chunk_id = f"chatcmpl-cache-{tp_req_id}"
                                init_chunk = {
                                    "id": chunk_id,
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model_name,
                                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                                }
                                yield f"data: {json.dumps(init_chunk)}\n\n".encode("utf-8")

                                if content_text:
                                    text_chunk = {
                                        "id": chunk_id,
                                        "object": "chat.completion.chunk",
                                        "created": int(time.time()),
                                        "model": model_name,
                                        "choices": [{"index": 0, "delta": {"content": content_text}, "finish_reason": None}],
                                    }
                                    yield f"data: {json.dumps(text_chunk)}\n\n".encode("utf-8")

                                final_chunk = {
                                    "id": chunk_id,
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model_name,
                                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                }
                                yield f"data: {json.dumps(final_chunk)}\n\n".encode("utf-8")
                                yield b"data: [DONE]\n\n"
                        finally:
                            total_dur = (time.perf_counter() - start_time) * 1000
                            asyncio.create_task(_persist_gateway_telemetry(
                                provider=clean_provider,
                                model=model_name,
                                status_code=200,
                                latency_ms=total_dur,
                                input_tokens=cached_entry.input_tokens,
                                output_tokens=cached_entry.output_tokens,
                                total_tokens=cached_entry.total_tokens,
                                cached_tokens=None,
                                reasoning_tokens=None,
                                ttft_ms=ttft_recorded,
                                stream_duration_ms=total_dur,
                                finish_reason="stop",
                                provider_request_id=f"cache_{cached_entry.cache_key[:12]}",
                                tokenpulse_request_id=tp_req_id,
                                cache_hit=True,
                            ))

                    return StreamingResponse(
                        cached_stream_generator(),
                        status_code=200,
                        headers=resp_headers,
                    )

    # 4. Fallback Candidates Setup & Monthly Budget Cap Check
    fallback_targets = await _get_fallback_targets(clean_provider, model_name)
    primary_budget_exceeded, total_spent, budget = await _is_provider_budget_exceeded(clean_provider)

    candidates: list[dict] = []
    if not primary_budget_exceeded:
        candidates.append({
            "provider": clean_provider,
            "model": model_name,
            "fallback_reason": None,
        })
    elif fallback_targets:
        logger.info(
            "Provider %s exceeded budget ($%.2f / $%.2f); routing directly to fallback targets",
            clean_provider, total_spent, budget
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Orçamento mensal do provedor '{clean_provider}' excedido (${round(total_spent, 2)} / ${budget:.2f}). Nenhuma regra de fallback configurada.",
        )

    # Add eligible fallback targets whose budget is not exceeded
    for target_prov, target_mod in fallback_targets:
        t_exceeded, _, _ = await _is_provider_budget_exceeded(target_prov)
        if not t_exceeded:
            candidates.append({
                "provider": target_prov,
                "model": target_mod,
                "fallback_reason": "budget_cap" if primary_budget_exceeded else None,
            })

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Orçamento mensal do provedor '{clean_provider}' excedido e todos os alvos de fallback também ultrapassaram o teto.",
        )

    client_auth = request.headers.get("authorization") or request.headers.get("x-api-key")

    # Fetch client from app.state or fallback
    client: httpx.AsyncClient = getattr(request.app.state, "http_client", None)
    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0))
        own_client = True

    try:
        for i, cand in enumerate(candidates):
            is_last = (i == len(candidates) - 1)
            curr_prov = cand["provider"]
            curr_mod = cand["model"]
            fb_reason = cand.get("fallback_reason")

            # Prepare body: if model changed, rewrite model field
            curr_body = body
            if curr_mod != model_name and body_json:
                mod_body = dict(body_json)
                mod_body["model"] = curr_mod
                curr_body = json.dumps(mod_body).encode("utf-8")

            # Resolve credentials and target URL for candidate
            try:
                api_key, base_url = await _resolve_provider_credentials(curr_prov, client_auth)
            except Exception as cred_err:
                if not is_last:
                    logger.warning("Could not resolve credentials for %s: %s; trying next fallback", curr_prov, cred_err)
                    continue
                raise

            # Normalize path
            target_path = subpath.lstrip("/")
            if curr_prov == "ollama":
                if not target_path.startswith("v1/") and not target_path.startswith("api/"):
                    target_path = f"v1/{target_path}"
                upstream_url = f"{base_url.rstrip('/')}/{target_path}"
            elif curr_prov in ("openai", "groq", "mistral"):
                if not target_path.startswith("v1/"):
                    target_path = f"v1/{target_path}"
                upstream_url = f"{base_url.rstrip('/')}/{target_path}"
            elif curr_prov in ("anthropic", "gemini"):
                upstream_url = f"{base_url.rstrip('/')}/{target_path}"

            # Query params
            query_params = dict(request.query_params)
            if curr_prov == "gemini" and api_key and "key" not in query_params:
                query_params["key"] = api_key

            # Outgoing headers
            out_headers: Dict[str, str] = {}
            for k, v in request.headers.items():
                if k.lower() not in HOP_BY_HOP_HEADERS:
                    out_headers[k] = v

            if "authorization" in out_headers and "tp_live_" in out_headers["authorization"]:
                out_headers.pop("authorization", None)

            if curr_prov in ("openai", "groq", "mistral", "ollama"):
                if api_key:
                    out_headers["authorization"] = f"Bearer {api_key}"
                else:
                    out_headers.pop("authorization", None)
            elif curr_prov == "anthropic" and api_key:
                out_headers["x-api-key"] = api_key
                if "anthropic-version" not in out_headers:
                    out_headers["anthropic-version"] = "2023-06-01"

            upstream_req = client.build_request(
                method=request.method,
                url=upstream_url,
                params=query_params,
                headers=out_headers,
                content=curr_body,
            )

            if not is_streaming:
                try:
                    upstream_resp = await client.send(upstream_req)
                except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                    if not is_last:
                        logger.warning("Upstream %s connection/timeout error: %s; trying fallback", curr_prov, net_err)
                        if i + 1 < len(candidates) and not candidates[i + 1].get("fallback_reason"):
                            candidates[i + 1]["fallback_reason"] = "timeout"
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail=f"Tempo limite esgotado ao comunicar com {curr_prov}.",
                    )

                # Check retryable status
                if upstream_resp.status_code in (429, 500, 502, 503, 504) and not is_last:
                    logger.warning("Upstream %s failed with HTTP %d; trying fallback", curr_prov, upstream_resp.status_code)
                    if i + 1 < len(candidates) and not candidates[i + 1].get("fallback_reason"):
                        candidates[i + 1]["fallback_reason"] = f"upstream_{upstream_resp.status_code}"
                    continue

                latency_ms = (time.perf_counter() - start_time) * 1000
                resp_bytes = upstream_resp.content
                resp_headers = {
                    k: v for k, v in upstream_resp.headers.items()
                    if k.lower() not in HOP_BY_HOP_HEADERS
                }
                resp_headers["X-TokenPulse-Request-Id"] = tp_req_id

                if fb_reason:
                    resp_headers["X-TokenPulse-Fallback"] = "true"
                    resp_headers["X-TokenPulse-Original-Provider"] = clean_provider
                    resp_headers["X-TokenPulse-Original-Model"] = model_name
                    resp_headers["X-TokenPulse-Actual-Provider"] = curr_prov
                    resp_headers["X-TokenPulse-Actual-Model"] = curr_mod
                    resp_headers["X-TokenPulse-Fallback-Reason"] = fb_reason

                input_tokens, output_tokens, total_tokens = None, None, None
                cached_tokens, reasoning_tokens, finish_reason = None, None, None
                provider_req_id = upstream_resp.headers.get("x-request-id")
                error_msg = None

                if upstream_resp.status_code == 200 and "application/json" in upstream_resp.headers.get("content-type", ""):
                    try:
                        resp_json = json.loads(resp_bytes.decode("utf-8"))
                        provider_req_id = resp_json.get("id") or provider_req_id
                        if curr_prov in ("openai", "groq", "mistral", "ollama"):
                            u = resp_json.get("usage") or {}
                            input_tokens = u.get("prompt_tokens")
                            output_tokens = u.get("completion_tokens")
                            total_tokens = u.get("total_tokens")
                            ptd = u.get("prompt_tokens_details") or {}
                            cached_tokens = ptd.get("cached_tokens")
                            ctd = u.get("completion_tokens_details") or {}
                            reasoning_tokens = ctd.get("reasoning_tokens")
                            choices = resp_json.get("choices") or []
                            if choices and isinstance(choices, list) and isinstance(choices[0], dict):
                                finish_reason = choices[0].get("finish_reason")
                        elif curr_prov == "anthropic":
                            u = resp_json.get("usage") or {}
                            input_tokens = u.get("input_tokens")
                            output_tokens = u.get("output_tokens")
                            total_tokens = (input_tokens + output_tokens) if input_tokens and output_tokens else None
                        elif curr_prov == "gemini":
                            u = resp_json.get("usageMetadata") or {}
                            input_tokens = u.get("promptTokenCount")
                            output_tokens = u.get("candidatesTokenCount")
                            total_tokens = u.get("totalTokenCount")
                    except Exception as parse_err:
                        logger.debug("Could not parse JSON usage: %s", parse_err)
                elif upstream_resp.status_code >= 400:
                    error_msg = redact_sensitive_text(resp_bytes.decode("utf-8", errors="replace")[:500])

                asyncio.create_task(_persist_gateway_telemetry(
                    provider=curr_prov,
                    model=curr_mod,
                    status_code=upstream_resp.status_code,
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    cached_tokens=cached_tokens,
                    reasoning_tokens=reasoning_tokens,
                    ttft_ms=None,
                    stream_duration_ms=None,
                    finish_reason=finish_reason,
                    provider_request_id=provider_req_id,
                    tokenpulse_request_id=tp_req_id,
                    error_msg=error_msg,
                    fallback_triggered=bool(fb_reason),
                    original_provider=clean_provider if fb_reason else None,
                    original_model=model_name if fb_reason else None,
                    fallback_reason=fb_reason,
                ))

                if not is_cache_bypassed:
                    resp_headers["X-TokenPulse-Cache"] = "MISS"

                if upstream_resp.status_code == 200 and cache_key and not is_cache_bypassed and not fb_reason:
                    _, _, estimated_saved_cost = _calculate_cost(curr_prov, curr_mod, input_tokens, output_tokens)
                    raw_text = resp_bytes.decode("utf-8", errors="ignore")
                    _dispatch_cache_persistence(
                        cache_key=cache_key,
                        provider=curr_prov,
                        model=curr_mod,
                        response_json=raw_text,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        total_tokens=total_tokens,
                        estimated_saved_cost=estimated_saved_cost,
                        ttl_seconds=req_cache_ttl,
                    )

                return Response(
                    content=resp_bytes,
                    status_code=upstream_resp.status_code,
                    headers=resp_headers,
                )
            else:
                # Streaming flow
                try:
                    upstream_resp = await client.send(upstream_req, stream=True)
                except (httpx.TimeoutException, httpx.ConnectError) as net_err:
                    if not is_last:
                        logger.warning("Upstream stream %s connection/timeout error: %s; trying fallback", curr_prov, net_err)
                        if i + 1 < len(candidates) and not candidates[i + 1].get("fallback_reason"):
                            candidates[i + 1]["fallback_reason"] = "timeout"
                        continue
                    raise HTTPException(
                        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                        detail=f"Tempo limite esgotado ao comunicar com {curr_prov}.",
                    )

                if upstream_resp.status_code in (429, 500, 502, 503, 504) and not is_last:
                    await upstream_resp.aclose()
                    logger.warning("Upstream stream %s failed with %d; trying fallback", curr_prov, upstream_resp.status_code)
                    if i + 1 < len(candidates) and not candidates[i + 1].get("fallback_reason"):
                        candidates[i + 1]["fallback_reason"] = f"upstream_{upstream_resp.status_code}"
                    continue

                resp_headers = {
                    k: v for k, v in upstream_resp.headers.items()
                    if k.lower() not in HOP_BY_HOP_HEADERS
                }
                resp_headers["X-TokenPulse-Request-Id"] = tp_req_id
                if not is_cache_bypassed:
                    resp_headers["X-TokenPulse-Cache"] = "MISS"

                if fb_reason:
                    resp_headers["X-TokenPulse-Fallback"] = "true"
                    resp_headers["X-TokenPulse-Original-Provider"] = clean_provider
                    resp_headers["X-TokenPulse-Original-Model"] = model_name
                    resp_headers["X-TokenPulse-Actual-Provider"] = curr_prov
                    resp_headers["X-TokenPulse-Actual-Model"] = curr_mod
                    resp_headers["X-TokenPulse-Fallback-Reason"] = fb_reason

                async def stream_generator() -> AsyncGenerator[bytes, None]:
                    ttft_recorded: Optional[float] = None
                    tokens_in: Optional[int] = None
                    tokens_out: Optional[int] = None
                    tokens_tot: Optional[int] = None
                    finish_res: Optional[str] = None
                    err_text: Optional[str] = None
                    accumulated_content: str = ""
                    provider_req_id: Optional[str] = upstream_resp.headers.get("x-request-id")

                    try:
                        async for chunk in upstream_resp.aiter_raw():
                            if not chunk:
                                continue
                            if ttft_recorded is None and chunk.strip():
                                ttft_recorded = (time.perf_counter() - start_time) * 1000

                            chunk_str = chunk.decode("utf-8", errors="ignore")
                            if "usage" in chunk_str or "choices" in chunk_str or "content_block_delta" in chunk_str or "delta" in chunk_str:
                                for line in chunk_str.splitlines():
                                    if line.startswith("data: ") and not line.strip() == "data: [DONE]":
                                        try:
                                            data = json.loads(line[6:].strip())
                                            provider_req_id = data.get("id") or provider_req_id
                                            usage_dict = data.get("usage")
                                            if usage_dict:
                                                tokens_in = usage_dict.get("prompt_tokens") or usage_dict.get("input_tokens") or tokens_in
                                                tokens_out = usage_dict.get("completion_tokens") or usage_dict.get("output_tokens") or tokens_out
                                                tokens_tot = usage_dict.get("total_tokens") or tokens_tot
                                            # OpenAI format
                                            choices = data.get("choices") or []
                                            if choices and isinstance(choices, list) and isinstance(choices[0], dict):
                                                delta = choices[0].get("delta") or {}
                                                delta_content = delta.get("content")
                                                if delta_content:
                                                    accumulated_content += delta_content
                                                f_reason = choices[0].get("finish_reason")
                                                if f_reason:
                                                    finish_res = f_reason
                                            # Anthropic format
                                            elif data.get("type") == "content_block_delta":
                                                delta_content = data.get("delta", {}).get("text")
                                                if delta_content:
                                                    accumulated_content += delta_content
                                            elif data.get("type") == "message_delta":
                                                f_reason = data.get("delta", {}).get("stop_reason")
                                                if f_reason:
                                                    finish_res = f_reason
                                        except Exception:
                                            pass
                            yield chunk

                    except asyncio.CancelledError:
                        err_text = "Client disconnected during streaming"
                        raise
                    except Exception as exc:
                        err_text = redact_sensitive_text(str(exc))
                        raise
                    finally:
                        await upstream_resp.aclose()
                        total_dur = (time.perf_counter() - start_time) * 1000

                        asyncio.create_task(_persist_gateway_telemetry(
                            provider=curr_prov,
                            model=curr_mod,
                            status_code=upstream_resp.status_code if not err_text else 499,
                            latency_ms=total_dur,
                            input_tokens=tokens_in,
                            output_tokens=tokens_out,
                            total_tokens=tokens_tot,
                            cached_tokens=None,
                            reasoning_tokens=None,
                            ttft_ms=ttft_recorded,
                            stream_duration_ms=total_dur,
                            finish_reason=finish_res,
                            provider_request_id=provider_req_id,
                            tokenpulse_request_id=tp_req_id,
                            error_msg=err_text,
                            fallback_triggered=bool(fb_reason),
                            original_provider=clean_provider if fb_reason else None,
                            original_model=model_name if fb_reason else None,
                            fallback_reason=fb_reason,
                        ))

                        if upstream_resp.status_code == 200 and cache_key and not is_cache_bypassed and not fb_reason and not err_text and accumulated_content:
                            if curr_prov == "anthropic":
                                cached_payload = {
                                    "id": provider_req_id or f"msg-{tp_req_id}",
                                    "type": "message",
                                    "role": "assistant",
                                    "model": curr_mod,
                                    "content": [{"type": "text", "text": accumulated_content}],
                                    "stop_reason": finish_res or "end_turn",
                                    "usage": {
                                        "input_tokens": tokens_in or 0,
                                        "output_tokens": tokens_out or 0,
                                    },
                                }
                            else:
                                cached_payload = {
                                    "id": provider_req_id or f"chatcmpl-{tp_req_id}",
                                    "object": "chat.completion",
                                    "created": int(time.time()),
                                    "model": curr_mod,
                                    "choices": [{
                                        "index": 0,
                                        "message": {"role": "assistant", "content": accumulated_content},
                                        "finish_reason": finish_res or "stop",
                                    }],
                                    "usage": {
                                        "prompt_tokens": tokens_in,
                                        "completion_tokens": tokens_out,
                                        "total_tokens": tokens_tot,
                                    },
                                }
                            _, _, estimated_saved_cost = _calculate_cost(curr_prov, curr_mod, tokens_in, tokens_out)
                            _dispatch_cache_persistence(
                                cache_key=cache_key,
                                provider=curr_prov,
                                model=curr_mod,
                                response_json=json.dumps(cached_payload),
                                input_tokens=tokens_in,
                                output_tokens=tokens_out,
                                total_tokens=tokens_tot,
                                estimated_saved_cost=estimated_saved_cost,
                                ttl_seconds=req_cache_ttl,
                            )

                return StreamingResponse(
                    stream_generator(),
                    status_code=upstream_resp.status_code,
                    headers=resp_headers,
                )

    except httpx.TimeoutException as te:
        dur = (time.perf_counter() - start_time) * 1000
        asyncio.create_task(_persist_gateway_telemetry(
            provider=clean_provider,
            model=model_name,
            status_code=504,
            latency_ms=dur,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cached_tokens=None,
            reasoning_tokens=None,
            ttft_ms=None,
            stream_duration_ms=None,
            finish_reason=None,
            provider_request_id=None,
            tokenpulse_request_id=tp_req_id,
            error_msg="Gateway timeout communicating with provider upstream.",
        ))
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Tempo limite esgotado ao comunicar com {clean_provider}.",
        )
    except httpx.RequestError as re:
        dur = (time.perf_counter() - start_time) * 1000
        asyncio.create_task(_persist_gateway_telemetry(
            provider=clean_provider,
            model=model_name,
            status_code=502,
            latency_ms=dur,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            cached_tokens=None,
            reasoning_tokens=None,
            ttft_ms=None,
            stream_duration_ms=None,
            finish_reason=None,
            provider_request_id=None,
            tokenpulse_request_id=tp_req_id,
            error_msg=redact_sensitive_text(str(re)),
        ))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Falha de conexão com upstream {clean_provider}: {redact_sensitive_text(str(re))}",
        )
    finally:
        if own_client:
            await client.aclose()


# -----------------------------------------------------------------------------
# Gateway Route Bindings
# -----------------------------------------------------------------------------

# Direct OpenAI SDK compatibility: client = OpenAI(base_url="http://127.0.0.1:8000/gateway/openai/v1")
@router.api_route(
    "/gateway/openai/v1/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="OpenAI-compatible Gateway Route",
)
async def gateway_openai_compatible(path: str, request: Request):
    return await _proxy_request(provider="openai", subpath=f"v1/{path}", request=request)


# Generalized Provider Gateway Route: /gateway/{provider}/{path}
@router.api_route(
    "/gateway/{provider}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
    summary="Universal Multi-Provider Gateway Route",
)
async def gateway_proxy_universal(provider: str, path: str, request: Request):
    return await _proxy_request(provider=provider, subpath=path, request=request)


# Gateway Health Check
@router.get("/api/gateway/health", summary="TokenPulse Gateway Health Check")
async def gateway_health():
    return {
        "status": "healthy",
        "gateway_enabled": settings.gateway_enabled,
        "supported_providers": list(DEFAULT_UPSTREAM_BASES.keys()),
        "telemetry_enabled": settings.telemetry_enabled,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
