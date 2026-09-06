"""
tests/test_usage_sync.py — Tests for direct provider usage synchronization and idempotency.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import pytest
import pytest_asyncio
import httpx
from unittest.mock import patch
from sqlalchemy import select, func

from main import app
from database import AsyncSessionLocal, init_db
from models import User, ProviderConfig, RequestLog


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
async def test_openai_direct_sync_and_idempotency():
    """Verify that OpenAI sync ingests usage logs and running it twice does not duplicate records."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register user
        reg = await client.post("/api/auth/register", json={
            "username": "sync_tester",
            "email": "sync_tester@example.com",
            "password": "Password123!",
        })
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Add OpenAI provider
        add_p = await client.post("/api/providers", json={
            "name": "openai",
            "display_name": "OpenAI Primary",
            "api_key": "sk-openai-sync-key-12345",
        }, headers=headers)
        assert add_p.status_code == 200

        # Mock OpenAI Organization Usage endpoint
        mock_openai_response = {
            "data": [
                {
                    "aggregation_timestamp": 1757116800,
                    "results": [
                        {
                            "model": "gpt-4o",
                            "input_tokens": 15000,
                            "output_tokens": 5000,
                            "num_model_requests": 10,
                        }
                    ],
                }
            ]
        }

        async def mock_get(self, url, *args, **kwargs):
            if "organization/usage" in str(url):
                return httpx.Response(200, json=mock_openai_response)
            return httpx.Response(404)

        with patch("httpx.AsyncClient.get", new=mock_get):
            # First sync run
            sync1 = await client.post("/api/sync/now", headers=headers)
            assert sync1.status_code == 200
            data1 = sync1.json()
            assert data1["status"] == "completed"
            assert "openai" in data1["synced_providers"]

            async with AsyncSessionLocal() as db:
                count1 = (await db.execute(select(func.count(RequestLog.id)))).scalar_one()
                assert count1 == 1

            # Second sync run (Idempotency verification)
            sync2 = await client.post("/api/sync/now", headers=headers)
            assert sync2.status_code == 200

            async with AsyncSessionLocal() as db:
                count2 = (await db.execute(select(func.count(RequestLog.id)))).scalar_one()
                # Must still be exactly 1 record, updated in-place without duplicating
                assert count2 == 1


@pytest.mark.asyncio
async def test_openrouter_direct_sync():
    """Verify that OpenRouter sync queries /auth/key and ingests usage and balance."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={
            "username": "or_tester",
            "email": "or_tester@example.com",
            "password": "Password123!",
        })
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Add OpenRouter provider
        add_p = await client.post("/api/providers", json={
            "name": "openrouter",
            "display_name": "OpenRouter Key",
            "api_key": "sk-or-v1-abcdef123456",
        }, headers=headers)
        assert add_p.status_code == 200

        mock_or_response = {
            "data": {
                "label": "Production Key",
                "usage": 24.50,
                "limit": 100.0,
                "is_free_tier": False,
            }
        }

        async def mock_get(self, url, *args, **kwargs):
            if "auth/key" in str(url):
                return httpx.Response(200, json=mock_or_response)
            return httpx.Response(404)

        with patch("httpx.AsyncClient.get", new=mock_get):
            sync_res = await client.post("/api/sync/now", headers=headers)
            assert sync_res.status_code == 200
            data = sync_res.json()
            assert "openrouter" in data["synced_providers"]
            assert data["results"]["openrouter"]["usage_usd"] == 24.50

        # Verify metrics updated (outside mock patch so test client talks to ASGI app)
        summary = await client.get("/api/metrics/summary", headers=headers)
        assert summary.status_code == 200
        today_cost = summary.json()["summary"]["today"]["cost"]
        assert today_cost == 24.50
