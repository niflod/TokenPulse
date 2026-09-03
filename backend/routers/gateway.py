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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal, get_db
from models import ProviderConfig, RequestLog
from pricing import lookup_pricing
from security import (
    OFFICIAL_PROVIDER_DOMAINS,
    redact_sensitive_text,
    require_admin,
    validate_provider_base_url,
)
from services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gateway"])

SupportedProvider = Literal["openai", "anthropic", "gemini"]

DEFAULT_UPSTREAM_BASES: Dict[str, str] = {
    "openai": "https://api.openai.com",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
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


# -----------------------------------------------------------------------------
# Gateway Helper Utilities
# -----------------------------------------------------------------------------

async def _resolve_provider_credentials(provider: str, client_auth_header: Optional[str]) -> tuple[Optional[str], str]:
    """
    Resolves the upstream API key and base URL.
    Uses incoming client key if provided, otherwise decrypts the key configured in DB.
    """
    clean_provider = provider.lower().strip()
    configured_base = DEFAULT_UPSTREAM_BASES.get(clean_provider, "https://api.openai.com")
    resolved_key = None

    # 1. Check if client sent an Authorization / API key header
    if client_auth_header and client_auth_header.strip():
        parts = client_auth_header.strip().split()
        candidate = parts[-1] if len(parts) > 1 else parts[0]
        # Only use if not a placeholder dummy key
        if candidate and not candidate.startswith("tp_dummy_"):
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
) -> None:
    """Saves telemetry asynchronously and emits event bus notification."""
    if not settings.telemetry_enabled:
        return

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
        })
    except Exception as e:
        logger.error("Failed to save gateway telemetry: %s", redact_sensitive_text(str(e)))


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

    tp_req_id = f"tp_req_{uuid.uuid4().hex[:16]}"
    start_time = time.perf_counter()

    # Read and inspect body
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

    # Resolve credentials and target URL
    client_auth = request.headers.get("authorization") or request.headers.get("x-api-key")
    api_key, base_url = await _resolve_provider_credentials(clean_provider, client_auth)

    # Normalize path
    target_path = subpath.lstrip("/")
    if clean_provider == "openai":
        if not target_path.startswith("v1/"):
            target_path = f"v1/{target_path}"
        upstream_url = f"{base_url.rstrip('/')}/{target_path}"
    elif clean_provider == "anthropic":
        upstream_url = f"{base_url.rstrip('/')}/{target_path}"
    elif clean_provider == "gemini":
        upstream_url = f"{base_url.rstrip('/')}/{target_path}"

    # Build upstream query params
    query_params = dict(request.query_params)
    if clean_provider == "gemini" and api_key and "key" not in query_params:
        query_params["key"] = api_key

    # Prepare sanitized upstream headers
    out_headers: Dict[str, str] = {}
    for k, v in request.headers.items():
        if k.lower() not in HOP_BY_HOP_HEADERS:
            out_headers[k] = v

    if clean_provider == "openai" and api_key:
        out_headers["authorization"] = f"Bearer {api_key}"
    elif clean_provider == "anthropic" and api_key:
        out_headers["x-api-key"] = api_key
        if "anthropic-version" not in out_headers:
            out_headers["anthropic-version"] = "2023-06-01"

    # Fetch client from app.state or fallback
    client: httpx.AsyncClient = getattr(request.app.state, "http_client", None)
    own_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=120.0))
        own_client = True

    try:
        upstream_req = client.build_request(
            method=request.method,
            url=upstream_url,
            params=query_params,
            headers=out_headers,
            content=body,
        )

        if not is_streaming:
            # -----------------------------------------------------------------
            # Non-Streaming Flow
            # -----------------------------------------------------------------
            upstream_resp = await client.send(upstream_req)
            latency_ms = (time.perf_counter() - start_time) * 1000

            resp_bytes = upstream_resp.content
            resp_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if k.lower() not in HOP_BY_HOP_HEADERS
            }
            resp_headers["X-TokenPulse-Request-Id"] = tp_req_id

            input_tokens = None
            output_tokens = None
            total_tokens = None
            cached_tokens = None
            reasoning_tokens = None
            finish_reason = None
            provider_req_id = upstream_resp.headers.get("x-request-id")
            error_msg = None

            if upstream_resp.status_code == 200 and "application/json" in upstream_resp.headers.get("content-type", ""):
                try:
                    resp_json = json.loads(resp_bytes.decode("utf-8"))
                    provider_req_id = resp_json.get("id") or provider_req_id
                    if clean_provider == "openai":
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
                    elif clean_provider == "anthropic":
                        u = resp_json.get("usage") or {}
                        input_tokens = u.get("input_tokens")
                        output_tokens = u.get("output_tokens")
                        total_tokens = (input_tokens + output_tokens) if input_tokens and output_tokens else None
                    elif clean_provider == "gemini":
                        u = resp_json.get("usageMetadata") or {}
                        input_tokens = u.get("promptTokenCount")
                        output_tokens = u.get("candidatesTokenCount")
                        total_tokens = u.get("totalTokenCount")
                except Exception as parse_err:
                    logger.debug("Could not parse JSON usage: %s", parse_err)
            elif upstream_resp.status_code >= 400:
                error_msg = redact_sensitive_text(resp_bytes.decode("utf-8", errors="replace")[:500])

            # Persist and broadcast
            asyncio.create_task(_persist_gateway_telemetry(
                provider=clean_provider,
                model=model_name,
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
            ))

            return Response(
                content=resp_bytes,
                status_code=upstream_resp.status_code,
                headers=resp_headers,
            )

        else:
            # -----------------------------------------------------------------
            # Streaming Flow (Real-time progressive chunking + TTFT calculation)
            # -----------------------------------------------------------------
            upstream_resp = await client.send(upstream_req, stream=True)
            resp_headers = {
                k: v for k, v in upstream_resp.headers.items()
                if k.lower() not in HOP_BY_HOP_HEADERS
            }
            resp_headers["X-TokenPulse-Request-Id"] = tp_req_id

            async def stream_generator() -> AsyncGenerator[bytes, None]:
                ttft_recorded: Optional[float] = None
                tokens_in: Optional[int] = None
                tokens_out: Optional[int] = None
                tokens_tot: Optional[int] = None
                finish_res: Optional[str] = None
                err_text: Optional[str] = None
                provider_req_id: Optional[str] = upstream_resp.headers.get("x-request-id")

                try:
                    async for chunk in upstream_resp.aiter_raw():
                        if not chunk:
                            continue
                        if ttft_recorded is None and chunk.strip():
                            ttft_recorded = (time.perf_counter() - start_time) * 1000

                        # Inspect SSE lines for usage
                        chunk_str = chunk.decode("utf-8", errors="ignore")
                        if "usage" in chunk_str:
                            for line in chunk_str.splitlines():
                                if line.startswith("data: ") and not line.strip() == "data: [DONE]":
                                    try:
                                        data = json.loads(line[6:].strip())
                                        provider_req_id = data.get("id") or provider_req_id
                                        u = data.get("usage")
                                        if u:
                                            tokens_in = u.get("prompt_tokens") or tokens_in
                                            tokens_out = u.get("completion_tokens") or tokens_out
                                            tokens_tot = u.get("total_tokens") or tokens_tot
                                        choices = data.get("choices") or []
                                        if choices and isinstance(choices, list) and isinstance(choices[0], dict):
                                            f_reason = choices[0].get("finish_reason")
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
                        provider=clean_provider,
                        model=model_name,
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
                    ))

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
