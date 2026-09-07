"""
tests/test_production_cors_and_post_setup.py — Verification for Production CORS, CSP environment splitting,
and dynamic post-setup route locking.
"""

import importlib
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import pytest
import pytest_asyncio
from config import settings
from database import AsyncSessionLocal, init_db
from main import app
from models import User
from sqlalchemy import delete


@pytest_asyncio.fixture(autouse=True)
async def clean_database():
    await init_db()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()


@pytest.mark.asyncio
async def test_netlify_production_origin_allowed_by_cors():
    """Verify preflight OPTIONS request from Netlify production origin is authorized."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.options(
            "/api/ping",
            headers={
                "Origin": "https://tknpulse.netlify.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "https://tknpulse.netlify.app"
        assert res.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_production_csp_excludes_localhost_and_ws(monkeypatch):
    """Verify CSP generated in production mode omits localhost and ws:."""
    import main as main_module
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "secret_key", "012345678901234567890123456789012345")

    prod_app = importlib.reload(main_module).app
    transport = httpx.ASGITransport(app=prod_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ping")
        csp = res.headers.get("Content-Security-Policy", "")
        assert "connect-src" in csp
        assert "localhost" not in csp
        assert "ws:" not in csp
        assert "https://tknpulse.netlify.app" in csp
        assert "https://tokenpulse-backend.onrender.com" in csp

    # Restore module
    monkeypatch.setattr(settings, "environment", "development")
    importlib.reload(main_module)


@pytest.mark.asyncio
async def test_post_setup_endpoint_is_locked_after_admin_created():
    """Verify /api/auth/setup is locked with 403 once an admin user exists."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Before any user: setup is accessible on localhost -> 200
        r1 = await client.post("/api/auth/setup", json={"username": "master_admin", "password": "Password123!"})
        assert r1.status_code == 200

        # 2. After user exists: setup endpoint is locked -> 409 Conflict
        r2 = await client.post("/api/auth/setup", json={"username": "second_admin", "password": "Password123!"})
        assert r2.status_code == 409
        assert "já" in r2.json()["detail"]
