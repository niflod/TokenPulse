"""
tests/test_provider_validation.py — Tests for provider validation and secure key storage.
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import pytest
import pytest_asyncio
import httpx
from unittest.mock import patch, AsyncMock

from main import app
from database import AsyncSessionLocal, init_db
from models import User, ProviderConfig


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProviderConfig))
        await db.execute(delete(User))
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProviderConfig))
        await db.execute(delete(User))
        await db.commit()


@pytest.mark.asyncio
async def test_provider_validation_success():
    """Verify that POST /api/providers/validate returns valid=True when upstream succeeds."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg = await client.post("/api/auth/register", json={
            "username": "tester",
            "email": "tester@example.com",
            "password": "Password123!",
        })
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Mock httpx.AsyncClient.get for OpenAI models
        async def mock_get(url, *args, **kwargs):
            return httpx.Response(200, json={"data": [{"id": "gpt-4o"}]})

        with patch("httpx.AsyncClient.get", new=mock_get):
            res = await client.post("/api/providers/validate", json={
                "name": "openai",
                "api_key": "sk-valid-test-key-12345678",
            }, headers=headers)

            assert res.status_code == 200
            data = res.json()
            assert data["valid"] is True
            assert "sucesso" in data["message"].lower()


@pytest.mark.asyncio
async def test_provider_validation_failure():
    """Verify that POST /api/providers/validate returns valid=False on upstream 401."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={
            "username": "tester_fail",
            "email": "tester_fail@example.com",
            "password": "Password123!",
        })
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        async def mock_get_fail(url, *args, **kwargs):
            return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

        with patch("httpx.AsyncClient.get", new=mock_get_fail):
            res = await client.post("/api/providers/validate", json={
                "name": "openai",
                "api_key": "sk-invalid-key-9999",
            }, headers=headers)

            assert res.status_code == 200
            data = res.json()
            assert data["valid"] is False
            assert "inválida" in data["message"].lower()


@pytest.mark.asyncio
async def test_provider_masked_key_returned():
    """Verify that ProviderResponse returns correctly masked key rather than plain text or all dots."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={
            "username": "tester_masked",
            "email": "tester_masked@example.com",
            "password": "Password123!",
        })
        token = reg.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Add provider
        raw_key = "sk-ant-live-secret-key-abcdef"
        add_res = await client.post("/api/providers", json={
            "name": "anthropic",
            "display_name": "Claude Test",
            "api_key": raw_key,
        }, headers=headers)
        assert add_res.status_code == 200

        # List providers
        list_res = await client.get("/api/providers", headers=headers)
        assert list_res.status_code == 200
        provs = list_res.json()
        assert len(provs) == 1
        p = provs[0]
        assert p["has_api_key"] is True
        # Masked key should show beginning and end
        assert p["masked_key"] == "sk-a...cdef"
        assert raw_key not in str(list_res.text)  # Plain secret never leaks in response
