"""
tests/test_multi_provider_sync.py — Tests for multi-provider usage sync, fault isolation and metric consolidation.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import pytest
import pytest_asyncio
import httpx
from unittest.mock import patch
from sqlalchemy import select

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
async def test_multi_provider_sync_and_fault_isolation():
    """
    Verify that sync runs across multiple providers (OpenAI, OpenRouter, Anthropic, Gemini, Groq),
    and if one provider fails, the others still sync successfully (fault isolation).
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg = await client.post("/api/auth/register", json={
            "username": "multi_sync_user",
            "email": "multi_sync@example.com",
            "password": "Password123!",
        })
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Add OpenAI provider
        await client.post("/api/providers", json={
            "name": "openai",
            "display_name": "OpenAI Account",
            "api_key": "sk-mock-openai-key-12345",
        }, headers=headers)

        # Add OpenRouter provider
        await client.post("/api/providers", json={
            "name": "openrouter",
            "display_name": "OpenRouter Account",
            "api_key": "sk-or-mock-key-12345",
        }, headers=headers)

        # Add Anthropic provider (will fail in mock to test fault isolation)
        await client.post("/api/providers", json={
            "name": "anthropic",
            "display_name": "Anthropic Broken Account",
            "api_key": "sk-ant-broken-key-12345",
        }, headers=headers)

        # Add Gemini provider
        await client.post("/api/providers", json={
            "name": "gemini",
            "display_name": "Gemini Account",
            "api_key": "AIzaSyMockGeminiKey-12345",
        }, headers=headers)

        # Mock responses
        async def mock_get(self, url, *args, **kwargs):
            url_str = str(url)
            if "openai.com" in url_str and "organization/usage" in url_str:
                return httpx.Response(200, json={
                    "data": [{
                        "aggregation_timestamp": 1757116800,
                        "results": [{
                            "model": "gpt-4o",
                            "input_tokens": 20000,
                            "output_tokens": 10000,
                        }]
                    }]
                })
            elif "openrouter.ai" in url_str and "auth/key" in url_str:
                return httpx.Response(200, json={
                    "data": {"label": "Key 1", "usage": 15.0, "limit": 50.0}
                })
            elif "anthropic.com" in url_str:
                # Simulate upstream failure on Anthropic
                return httpx.Response(500, text="Internal Server Error from Anthropic")
            elif "generativelanguage.googleapis.com" in url_str:
                return httpx.Response(200, json={"models": [{"name": "models/gemini-1.5-pro"}]})
            return httpx.Response(404)

        with patch("httpx.AsyncClient.get", new=mock_get):
            sync_res = await client.post("/api/sync/now", headers=headers)
            assert sync_res.status_code == 200
            data = sync_res.json()

            # OpenAI, OpenRouter, and Gemini must succeed
            assert "openai" in data["synced_providers"]
            assert "openrouter" in data["synced_providers"]
            assert "gemini" in data["synced_providers"]

            # Anthropic must fail gracefully without aborting the other providers
            assert "anthropic" not in data["synced_providers"]
            assert data["results"]["anthropic"]["status"] == "error"

        # Check DB provider status
        async with AsyncSessionLocal() as db:
            provs = (await db.execute(select(ProviderConfig))).scalars().all()
            prov_map = {p.name: p for p in provs}
            assert prov_map["openai"].sync_status == "success"
            assert prov_map["openrouter"].sync_status == "success"
            assert prov_map["gemini"].sync_status == "success"
            assert prov_map["anthropic"].sync_status == "error"
            assert "HTTP 500" in prov_map["anthropic"].sync_error

        # Verify unified metrics aggregation across all synced data
        summary_res = await client.get("/api/metrics/summary", headers=headers)
        assert summary_res.status_code == 200
        summary_data = summary_res.json()
        assert summary_data["summary"]["today"]["cost"] is not None
        assert summary_data["summary"]["today"]["cost"] > 0
