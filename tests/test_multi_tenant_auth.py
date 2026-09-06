"""
tests/test_multi_tenant_auth.py — Tests for multi-tenant registration, auth, and tenant isolation.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import select

from main import app
from database import AsyncSessionLocal, init_db
from models import User, ProviderConfig, ClientApiKey, RequestLog


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()
    from sqlalchemy import delete
    from services.aggregator import aggregator
    aggregator.clear_cache()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RequestLog))
        await db.execute(delete(ProviderConfig))
        await db.execute(delete(User))
        await db.commit()
    yield
    aggregator.clear_cache()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RequestLog))
        await db.execute(delete(ProviderConfig))
        await db.execute(delete(User))
        await db.commit()


@pytest.mark.asyncio
async def test_user_registration_and_login():
    """Verify open public user registration and subsequent login."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register new user
        reg_payload = {
            "username": "tenant_alice",
            "email": "alice@example.com",
            "password": "SecurePassword123!",
        }
        res = await client.post("/api/auth/register", json=reg_payload)
        assert res.status_code == 201
        data = res.json()
        assert data["username"] == "tenant_alice"
        assert "token" in data
        assert data["expires_in"] > 0

        # 2. Conflict on duplicate username
        res_dup_user = await client.post("/api/auth/register", json={
            "username": "tenant_alice",
            "email": "another@example.com",
            "password": "SecurePassword123!",
        })
        assert res_dup_user.status_code == 409

        # 3. Conflict on duplicate email
        res_dup_email = await client.post("/api/auth/register", json={
            "username": "another_user",
            "email": "alice@example.com",
            "password": "SecurePassword123!",
        })
        assert res_dup_email.status_code == 409

        # 4. Login with registered user
        login_res = await client.post("/api/auth/login", json={
            "username": "tenant_alice",
            "password": "SecurePassword123!",
        })
        assert login_res.status_code == 200
        assert "token" in login_res.json()


@pytest.mark.asyncio
async def test_multi_tenant_provider_isolation():
    """Verify that User A cannot see, update, or delete User B's provider configurations."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User A
        res_a = await client.post("/api/auth/register", json={
            "username": "user_a",
            "email": "user_a@example.com",
            "password": "Password123!",
        })
        token_a = res_a.json()["token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Register User B
        res_b = await client.post("/api/auth/register", json={
            "username": "user_b",
            "email": "user_b@example.com",
            "password": "Password123!",
        })
        token_b = res_b.json()["token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A adds openai provider
        prov_a_res = await client.post("/api/providers", json={
            "name": "openai",
            "display_name": "Alice OpenAI",
            "api_key": "sk-alice-test-key",
        }, headers=headers_a)
        assert prov_a_res.status_code in (200, 201)

        # User B adds openai provider with different display name
        prov_b_res = await client.post("/api/providers", json={
            "name": "openai",
            "display_name": "Bob OpenAI",
            "api_key": "sk-bob-test-key",
        }, headers=headers_b)
        assert prov_b_res.status_code in (200, 201)

        # User A lists providers: sees Alice OpenAI, NOT Bob OpenAI
        list_a = await client.get("/api/providers", headers=headers_a)
        assert list_a.status_code == 200
        providers_a = list_a.json()
        names_a = [p["display_name"] for p in providers_a]
        assert "Alice OpenAI" in names_a
        assert "Bob OpenAI" not in names_a

        # User B lists providers: sees Bob OpenAI, NOT Alice OpenAI
        list_b = await client.get("/api/providers", headers=headers_b)
        assert list_b.status_code == 200
        providers_b = list_b.json()
        names_b = [p["display_name"] for p in providers_b]
        assert "Bob OpenAI" in names_b
        assert "Alice OpenAI" not in names_b

        # User B cannot delete User A's provider
        del_res = await client.delete("/api/providers/openai", headers=headers_b)
        # B deletes own openai
        assert del_res.status_code in (200, 204)

        # User A's provider must still exist
        list_a_after = await client.get("/api/providers", headers=headers_a)
        assert any(p["display_name"] == "Alice OpenAI" for p in list_a_after.json())


@pytest.mark.asyncio
async def test_multi_tenant_metrics_and_logs_isolation():
    """Verify that User A's request logs and metrics are not visible or aggregated for User B."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register User A
        res_a = await client.post("/api/auth/register", json={
            "username": "user_a",
            "email": "user_a@example.com",
            "password": "Password123!",
        })
        token_a = res_a.json()["token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Register User B
        res_b = await client.post("/api/auth/register", json={
            "username": "user_b",
            "email": "user_b@example.com",
            "password": "Password123!",
        })
        token_b = res_b.json()["token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # User A logs a request
        res_log_a = await client.post("/api/logs", json={
            "provider": "openai",
            "model": "gpt-4o",
            "input_tokens": 100,
            "output_tokens": 200,
            "cost_input": 0.00025,
            "cost_output": 0.002,
            "status_code": 200,
            "latency_ms": 450.0,
        }, headers=headers_a)
        assert res_log_a.status_code == 201

        # User A queries logs: 1 item
        logs_a = await client.get("/api/logs", headers=headers_a)
        assert logs_a.status_code == 200
        assert logs_a.json()["total"] == 1

        # User B queries logs: 0 items (strict tenant isolation)
        logs_b = await client.get("/api/logs", headers=headers_b)
        assert logs_b.status_code == 200
        assert logs_b.json()["total"] == 0

        # User A checks metrics summary: requests = 1, tokens = 300
        metrics_a = await client.get("/api/metrics/summary", headers=headers_a)
        assert metrics_a.status_code == 200
        assert metrics_a.json()["summary"]["today"]["requests"] == 1
        assert metrics_a.json()["summary"]["today"]["totalTokens"] == 300

        # User B checks metrics summary: requests = 0, tokens = 0
        metrics_b = await client.get("/api/metrics/summary", headers=headers_b)
        assert metrics_b.status_code == 200
        assert metrics_b.json()["summary"]["today"]["requests"] == 0
        assert metrics_b.json()["summary"]["today"]["totalTokens"] == 0
