"""
tests/test_gateway_key_rate_limit.py — Test per-key rate limiting (ClientApiKey.rate_limit_rpm) in the Gateway.
"""

import hashlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import pytest
from config import settings
from database import AsyncSessionLocal, init_db
from main import app
from models import ClientApiKey
from security import gateway_rate_limiter
from sqlalchemy import delete


@pytest.mark.asyncio
async def test_gateway_enforces_per_key_rate_limit(monkeypatch):
    """Verify that a virtual key with rate_limit_rpm=3 is throttled on the 4th request."""
    from services.aggregator import aggregator
    monkeypatch.setattr(settings, "gateway_require_auth", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-mock-key")
    aggregator.register_provider("openai", api_key="sk-test-mock-key")
    gateway_rate_limiter.reset()
    await init_db()

    # 1. Create a key with rate_limit_rpm = 3
    raw_key = f"tp_live_custom_rpm_{uuid.uuid4().hex[:12]}"
    k_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async with AsyncSessionLocal() as db:
        key_rec = ClientApiKey(
            name="Limited Key 3 RPM",
            key_hash=k_hash,
            key_prefix=raw_key[:12],
            rate_limit_rpm=3,
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(key_rec)
        await db.commit()

    try:
        def mock_upstream(req: httpx.Request):
            return httpx.Response(
                200,
                json={"id": "chatcmpl-mock", "choices": [{"message": {"content": "ok"}}]},
            )

        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"Authorization": f"Bearer {raw_key}"}
            payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "ping"}]}

            # First 3 requests -> 200 OK
            for i in range(3):
                res = await client.post(
                    "/gateway/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                assert res.status_code == 200, f"Request {i+1} failed with status {res.status_code}"

            # 4th request -> 429 Too Many Requests with Retry-After
            throttled_res = await client.post(
                "/gateway/openai/v1/chat/completions",
                headers=headers,
                json=payload,
            )
            assert throttled_res.status_code == 429
            assert "Retry-After" in throttled_res.headers
            assert int(throttled_res.headers["Retry-After"]) >= 1
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ClientApiKey).where(ClientApiKey.key_hash == k_hash))
            await db.commit()
