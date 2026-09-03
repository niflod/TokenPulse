"""
tests/test_fallback.py — Tests for model fallback rules CRUD and failover engine.
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
from models import FallbackRule
from routers.auth import create_access_token


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    await init_db()
    from services.cache_service import flush_all_cache
    async with AsyncSessionLocal() as db:
        await flush_all_cache(db)
    yield


@pytest.mark.asyncio
async def test_fallback_rules_crud():
    token, _ = create_access_token("admin")
    auth_headers = {"Authorization": f"Bearer {token}"}

    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
        # 1. List seeded default rules
        res = await client.get("/api/fallback-rules", headers=auth_headers)
        assert res.status_code == 200
        rules = res.json()
        assert len(rules) >= 4
        # Verify default gpt-4o -> groq rule exists
        gpt4o_rules = [r for r in rules if r["source_model"] == "gpt-4o"]
        assert len(gpt4o_rules) >= 1
        assert gpt4o_rules[0]["target_provider"] in ("groq", "mistral")

        # 2. Create custom rule
        new_rule_data = {
            "source_provider": "openai",
            "source_model": "o1-preview",
            "target_provider": "groq",
            "target_model": "llama-3.3-70b-versatile",
            "priority": 1,
            "enabled": True,
        }
        create_res = await client.post("/api/fallback-rules", json=new_rule_data, headers=auth_headers)
        assert create_res.status_code == 201
        created = create_res.json()
        rule_id = created["id"]
        assert created["source_model"] == "o1-preview"
        assert created["priority"] == 1

        # 3. Toggle rule
        toggle_res = await client.put(f"/api/fallback-rules/{rule_id}/toggle", headers=auth_headers)
        assert toggle_res.status_code == 200
        assert toggle_res.json()["enabled"] is False

        # 4. Delete rule
        del_res = await client.delete(f"/api/fallback-rules/{rule_id}", headers=auth_headers)
        assert del_res.status_code == 204

        # 5. Confirm deletion
        list_again = await client.get("/api/fallback-rules", headers=auth_headers)
        ids = [r["id"] for r in list_again.json()]
        assert rule_id not in ids


@pytest.mark.asyncio
async def test_gateway_failover_on_429():
    """Verify when primary provider returns 429, gateway redirects to fallback target."""
    requests_made = []

    def mock_handler(req: httpx.Request):
        requests_made.append(str(req.url))
        if "api.openai.com" in str(req.url):
            return httpx.Response(429, json={"error": "Rate limit reached"})
        elif "api.groq.com" in str(req.url):
            import json
            req_body = json.loads(req.content.decode("utf-8"))
            # Model field was rewritten to fallback target model
            assert req_body.get("model") == "llama-3.3-70b-versatile"
            return httpx.Response(200, json={
                "id": "groq-fb-1",
                "choices": [{"message": {"content": "Hello from Groq Fallback!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            })
        return httpx.Response(500)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": "Bearer sk-primary-openai-key"},
            )
            assert res.status_code == 200
            data = res.json()
            assert "Hello from Groq Fallback!" in data["choices"][0]["message"]["content"]
            # Verify telemetry response headers
            assert res.headers.get("X-TokenPulse-Fallback") == "true"
            assert res.headers.get("X-TokenPulse-Original-Provider") == "openai"
            assert res.headers.get("X-TokenPulse-Original-Model") == "gpt-4o"
            assert res.headers.get("X-TokenPulse-Actual-Provider") == "groq"
            assert res.headers.get("X-TokenPulse-Actual-Model") == "llama-3.3-70b-versatile"
            assert res.headers.get("X-TokenPulse-Fallback-Reason") == "upstream_429"

            # Verify persisted RequestLog has fallback metadata
            from models import RequestLog
            import asyncio
            await asyncio.sleep(0.1)  # Let async task persist
            async with AsyncSessionLocal() as db:
                stmt = select(RequestLog).order_by(RequestLog.id.desc()).limit(1)
                log = (await db.execute(stmt)).scalar_one_or_none()
                assert log is not None
                assert log.fallback_triggered is True
                assert log.original_provider == "openai"
                assert log.original_model == "gpt-4o"
                assert log.provider == "groq"
                assert log.model == "llama-3.3-70b-versatile"
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_failover_on_500():
    """Verify when primary provider returns 500, gateway redirects to fallback target."""
    def mock_handler(req: httpx.Request):
        if "api.openai.com" in str(req.url):
            return httpx.Response(500, json={"error": "Internal server error"})
        elif "api.groq.com" in str(req.url):
            return httpx.Response(200, json={
                "id": "groq-fb-2",
                "choices": [{"message": {"content": "Recovered by Groq!"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            })
        return httpx.Response(502)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
            assert res.status_code == 200
            assert res.headers.get("X-TokenPulse-Fallback") == "true"
            assert res.headers.get("X-TokenPulse-Fallback-Reason") == "upstream_500"
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_failover_on_timeout():
    """Verify when primary provider times out, gateway redirects to fallback target."""
    def mock_handler(req: httpx.Request):
        if "api.openai.com" in str(req.url):
            raise httpx.ConnectTimeout("Connection timed out to openai")
        elif "api.groq.com" in str(req.url):
            return httpx.Response(200, json={
                "id": "groq-fb-3",
                "choices": [{"message": {"content": "Recovered from Timeout!"}}],
            })
        return httpx.Response(502)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
            assert res.status_code == 200
            assert res.headers.get("X-TokenPulse-Fallback") == "true"
            assert res.headers.get("X-TokenPulse-Fallback-Reason") == "timeout"
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_failover_on_budget_cap():
    """Verify when primary provider budget is exceeded, gateway routes directly to fallback."""
    import config
    from models import RequestLog
    from datetime import datetime, timezone

    # Configure small budget
    config.settings.provider_monthly_budget = 10.0

    async with AsyncSessionLocal() as db:
        # Seed log that exceeds budget for openai ($15 > $10)
        db.add(RequestLog(
            provider="openai",
            model="gpt-4o",
            timestamp=datetime.now(timezone.utc),
            cost_total=15.0,
            status_code=200,
        ))
        await db.commit()

    called_urls = []
    def mock_handler(req: httpx.Request):
        called_urls.append(str(req.url))
        return httpx.Response(200, json={
            "id": "groq-budget-fb",
            "choices": [{"message": {"content": "Budget cap failover active!"}}],
        })

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            )
            assert res.status_code == 200
            # Primary OpenAI was NEVER called because budget was already exceeded!
            assert not any("api.openai.com" in u for u in called_urls)
            # Directly called Groq
            assert any("api.groq.com" in u for u in called_urls)
            assert res.headers.get("X-TokenPulse-Fallback") == "true"
            assert res.headers.get("X-TokenPulse-Fallback-Reason") == "budget_cap"
    finally:
        config.settings.provider_monthly_budget = 0.0
        await mock_client.aclose()

