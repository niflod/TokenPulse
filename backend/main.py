"""
main.py — FastAPI entrypoint for AI Usage Dashboard.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal, init_db
from models import AlertConfig, ProviderConfig
from routers import (
    alerts_router,
    export_router,
    gateway_router,
    health_router,
    logs_router,
    metrics_router,
    models_router,
    providers_router,
    realtime_router,
)
from routers.api_keys import router as api_keys_router
from routers.auth import router as auth_router
from routers.cache_router import router as cache_router
from routers.fallback_rules import router as fallback_rules_router
from services.aggregator import aggregator

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown hook."""
    logger.info("Starting AI Usage Dashboard backend...")
    await init_db()

    # Seed default AlertConfigs and register active providers from DB
    async with AsyncSessionLocal() as db:
        # 1. Alert defaults
        res = await db.execute(select(AlertConfig))
        existing_alerts = res.scalars().all()
        if not existing_alerts:
            defaults = [
                AlertConfig(provider="all", metric="daily_usage_pct", threshold=80.0, enabled=True),
                AlertConfig(provider="all", metric="error_rate", threshold=5.0, enabled=True),
                AlertConfig(provider="all", metric="latency_ms", threshold=2000.0, enabled=True),
            ]
            db.add_all(defaults)
            await db.commit()
            logger.info("Initialized default alert rules.")

        # 2. Register providers from DB into aggregator
        p_res = await db.execute(select(ProviderConfig).where(ProviderConfig.enabled == True))
        providers = p_res.scalars().all()
        secret = settings.get_fernet_key()

        for p in providers:
            raw_key = p.decrypt_key(secret)
            aggregator.register_provider(p.name, api_key=raw_key, base_url=p.base_url)

        # 3. Check for pre-configured env keys if not already in DB
        env_providers = [
            ("openai", "OpenAI", settings.openai_api_key),
            ("anthropic", "Anthropic", settings.anthropic_api_key),
            ("gemini", "Google Gemini", settings.gemini_api_key),
        ]
        for name, disp, key in env_providers:
            if key and not aggregator.get_adapter(name):
                aggregator.register_provider(name, api_key=key)
                logger.info("Loaded provider '%s' from environment variable.", name)

    limits = httpx.Limits(max_keepalive_connections=20, max_connections=100)
    timeout = httpx.Timeout(
        connect=settings.gateway_connect_timeout,
        read=settings.gateway_read_timeout,
        write=30.0,
        pool=10.0,
    )
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        app.state.http_client = client
        if not settings.admin_api_key:
            logger.warning("ATENÇÃO DE SEGURANÇA: ADMIN_API_KEY não configurada. Defina ADMIN_API_KEY no .env para proteger rotas de mutação em produção.")

        logger.info("TokenPulse backend ready on http://%s:%s", settings.host, settings.port)
        yield
        logger.info("Shutting down TokenPulse backend.")


app = FastAPI(
    title="TokenPulse — Observe your AI",
    description="Observability and real-time usage monitoring for AI APIs (OpenAI, Anthropic, Gemini)",
    version="1.1.0",
    lifespan=lifespan,
)

# CORS middleware — restricted to trusted local origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key", "Authorization", "x-api-key", "anthropic-version"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Inject robust security headers and Content-Security-Policy on every response."""
    response = await call_next(request)
    csp = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' http://localhost:* http://127.0.0.1:* ws:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self';"
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
    )
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Paths that bypass JWT authentication (handled by own auth or public)
_PUBLIC_PREFIXES = (
    "/api/auth/login",
    "/api/auth/setup",
    "/api/auth/status",
    "/api/ping",
    "/api/gateway/health",
    "/gateway",
    "/docs",
    "/openapi.json",
    "/redoc",
)
_STATIC_EXTENSIONS = (".html", ".css", ".js", ".ico", ".png", ".svg", ".woff", ".woff2", ".ttf", ".map")


@app.middleware("http")
async def jwt_auth_middleware(request, call_next):
    """Global JWT protection. Rejects unauthenticated requests to protected endpoints."""
    from starlette.responses import JSONResponse

    path = request.url.path

    # Allow static files and public API paths
    if path == "/" or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await call_next(request)

    # Allow static file extensions (CSS, JS, images, fonts)
    if any(path.endswith(ext) for ext in _STATIC_EXTENSIONS):
        return await call_next(request)

    # Check JWT token from Authorization header or disposable ticket for SSE
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif path == "/api/realtime/stream":
        ticket = request.query_params.get("ticket")
        if ticket:
            from routers.realtime import validate_and_consume_ticket
            if validate_and_consume_ticket(ticket):
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Ticket de stream SSE inválido ou expirado."},
                headers={"WWW-Authenticate": "Bearer"},
            )

    if token:
        try:
            from routers.auth import decode_access_token
            decode_access_token(token)
            return await call_next(request)
        except Exception:
            return JSONResponse(
                status_code=401,
                content={"detail": "Token inválido ou expirado."},
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Also accept X-Admin-Key for backwards compatibility
    admin_key = request.headers.get("x-admin-key", "")
    if admin_key and settings.admin_api_key:
        import hmac
        if hmac.compare_digest(admin_key.encode(), settings.admin_api_key.encode()):
            return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={"detail": "Autenticação necessária. Faça login em /login.html"},
        headers={"WWW-Authenticate": "Bearer"},
    )

# Register API Routers
app.include_router(auth_router)
app.include_router(api_keys_router)
app.include_router(cache_router)
app.include_router(fallback_rules_router)
app.include_router(metrics_router)
app.include_router(providers_router)
app.include_router(models_router)
app.include_router(logs_router)
app.include_router(health_router)
app.include_router(alerts_router)
app.include_router(export_router)
app.include_router(realtime_router)
app.include_router(gateway_router)


@app.get("/api/ping")
async def ping():
    """Health ping endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.1.0",
    }


# Mount frontend static files if directory exists
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info("Mounted frontend static files from %s", frontend_path)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
