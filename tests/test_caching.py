import os
import sys
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import engine, Base, AsyncSessionLocal, init_db
from models import GatewayResponseCache
from services.cache_service import (
    compute_gateway_cache_key,
    get_cached_response,
    set_cached_response,
    flush_all_cache,
    get_cache_statistics,
)


@pytest_asyncio.fixture(autouse=True)
async def prepare_db() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_db()
    async with AsyncSessionLocal() as db:
        await flush_all_cache(db)
    yield


def test_compute_gateway_cache_key_determinism():
    """Verify that identical semantic requests produce identical keys regardless of key order or stream flag."""
    body1 = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Hello world"}],
        "temperature": 0.7,
        "stream": True,
    }
    body2 = {
        "stream": False,
        "temperature": 0.7,
        "messages": [{"role": "user", "content": "Hello world"}],
        "model": "gpt-4o",
    }
    key1 = compute_gateway_cache_key("openai", "gpt-4o", body1)
    key2 = compute_gateway_cache_key("OpenAI ", "gpt-4o", body2)
    assert key1 == key2
    assert len(key1) == 64

    # Changing temperature or prompt changes the key
    body3 = dict(body1, temperature=0.9)
    key3 = compute_gateway_cache_key("openai", "gpt-4o", body3)
    assert key1 != key3


@pytest.mark.asyncio
async def test_cache_service_set_get_and_expiration():
    """Verify write, read with hit count increment, and expiration filtering."""
    async with AsyncSessionLocal() as db:
        key = "test_sha256_hash_12345"
        resp_json = '{"id":"test","choices":[{"message":{"content":"Cached response"}}]}'

        # 1. Set cache entry with 2 second TTL
        await set_cached_response(
            db=db,
            cache_key=key,
            provider="openai",
            model="gpt-4o",
            response_json=resp_json,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            estimated_saved_cost=0.0002,
            ttl_seconds=2,
        )

        # 2. Get unexpired cache entry
        hit1 = await get_cached_response(db, key)
        assert hit1 is not None
        assert hit1.hit_count == 1
        assert "Cached response" in hit1.response_json

        hit2 = await get_cached_response(db, key)
        assert hit2 is not None
        assert hit2.hit_count == 2

        # 3. Test stats
        stats = await get_cache_statistics(db)
        assert stats["active_entries"] == 1
        assert stats["total_hits"] == 2
        assert stats["total_saved_cost_usd"] > 0

        # 4. Simulate expiration
        hit2.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db.commit()

        expired_check = await get_cached_response(db, key)
        assert expired_check is None

        # 5. Test flush
        deleted = await flush_all_cache(db)
        assert deleted >= 1


@pytest.mark.asyncio
async def test_gateway_cache_miss_then_hit_json():
    """Verify first request MISSes and caches; second request HITs in cache with $0.00 cost."""
    import httpx
    from main import app
    import asyncio

    upstream_calls = 0

    def mock_handler(req: httpx.Request):
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200, json={
            "id": "chatcmpl-live-1",
            "choices": [{"message": {"content": "Fresh response from upstream"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
        })

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            payload = {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "What is the capital of France?"}],
                "temperature": 0.0,
            }

            # 1. First Request -> MISS
            res1 = await client.post("/gateway/openai/v1/chat/completions", json=payload)
            assert res1.status_code == 200
            assert res1.headers.get("X-TokenPulse-Cache") == "MISS"
            assert upstream_calls == 1
            data1 = res1.json()
            assert "Fresh response from upstream" in data1["choices"][0]["message"]["content"]

            await asyncio.sleep(0.15)  # Allow background caching to complete

            # 2. Second Request -> HIT
            res2 = await client.post("/gateway/openai/v1/chat/completions", json=payload)
            assert res2.status_code == 200
            assert res2.headers.get("X-TokenPulse-Cache") == "HIT"
            assert res2.headers.get("X-TokenPulse-Cache-Age") is not None
            # Upstream was NOT called a second time!
            assert upstream_calls == 1

            # 3. Verify telemetry in RequestLog
            from models import RequestLog
            from sqlalchemy import select
            await asyncio.sleep(0.1)
            async with AsyncSessionLocal() as db:
                stmt = select(RequestLog).order_by(RequestLog.id.desc()).limit(1)
                log = (await db.execute(stmt)).scalar_one_or_none()
                assert log is not None
                assert log.cache_hit is True
                assert log.cost_total == 0.0
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_cache_bypass_header():
    """Verify X-TokenPulse-Cache: false forces an upstream call even when cached."""
    import httpx
    from main import app
    import asyncio

    upstream_calls = 0

    def mock_handler(req: httpx.Request):
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200, json={
            "id": f"chatcmpl-live-{upstream_calls}",
            "choices": [{"message": {"content": f"Response {upstream_calls}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            payload = {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Bypass test prompt"}],
            }

            # Prime the cache
            res1 = await client.post("/gateway/openai/v1/chat/completions", json=payload)
            assert res1.status_code == 200
            assert upstream_calls == 1

            await asyncio.sleep(0.15)

            # Bypass cache
            res2 = await client.post(
                "/gateway/openai/v1/chat/completions",
                json=payload,
                headers={"X-TokenPulse-Cache": "false"},
            )
            assert res2.status_code == 200
            assert res2.headers.get("X-TokenPulse-Cache") is None
            # Upstream was called again!
            assert upstream_calls == 2
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_cache_streaming_sse_hit():
    """Verify streaming request hits cache and reconstructs valid SSE chunks."""
    import httpx
    from main import app
    import asyncio

    upstream_calls = 0

    def mock_handler(req: httpx.Request):
        nonlocal upstream_calls
        upstream_calls += 1
        return httpx.Response(200, json={
            "id": "chatcmpl-prime",
            "choices": [{"message": {"content": "Hello streaming world!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        })

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            payload_base = {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Tell me something for stream"}],
            }

            # 1. Prime cache with non-streaming
            res1 = await client.post("/gateway/openai/v1/chat/completions", json=payload_base)
            assert res1.status_code == 200
            assert upstream_calls == 1

            await asyncio.sleep(0.15)

            # 2. Second request with stream=True -> STREAMING CACHE HIT!
            stream_payload = dict(payload_base, stream=True)
            res2 = await client.post("/gateway/openai/v1/chat/completions", json=stream_payload)
            assert res2.status_code == 200
            assert res2.headers.get("X-TokenPulse-Cache") == "HIT"
            assert "text/event-stream" in res2.headers.get("content-type", "")

            # Verify SSE chunks
            chunks_received = res2.text
            assert "data: " in chunks_received
            assert "Hello streaming world!" in chunks_received
            assert "data: [DONE]" in chunks_received
            # Upstream was NOT called again!
            assert upstream_calls == 1
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_cache_management_endpoints():
    """Verify REST endpoints: stats, config update, flush, and JWT authentication enforcement."""
    import httpx
    from main import app
    from routers.auth import create_access_token

    token, _ = create_access_token("admin")
    auth_headers = {"Authorization": f"Bearer {token}"}

    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
        # 1. Unauthorized without JWT
        unauth_res = await client.get("/api/cache/stats")
        assert unauth_res.status_code == 401

        # 2. Get Stats with JWT
        stats_res = await client.get("/api/cache/stats", headers=auth_headers)
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert "active_entries" in stats
        assert "total_saved_cost_usd" in stats
        assert "cache_hit_rate_pct" in stats

        # 3. Get Config
        config_res = await client.get("/api/cache/config", headers=auth_headers)
        assert config_res.status_code == 200
        assert config_res.json()["enabled"] is True

        # 4. Update Config
        upd_res = await client.put(
            "/api/cache/config",
            json={"enabled": True, "default_ttl": 7200},
            headers=auth_headers,
        )
        assert upd_res.status_code == 200
        assert upd_res.json()["default_ttl_seconds"] == 7200

        # 5. Flush Cache
        flush_res = await client.post("/api/cache/flush", headers=auth_headers)
        assert flush_res.status_code == 200
        assert flush_res.json()["status"] == "ok"


