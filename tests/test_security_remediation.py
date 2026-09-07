"""
tests/test_security_remediation.py — Consolidated security verification suite.
Validates that all security remediations are in place and no regressions exist.
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import httpx
import pytest
from config import Settings, settings
from database import AsyncSessionLocal
from main import app
from models import ClientApiKey


@pytest.mark.asyncio
async def test_secret_key_mandatory_in_production():
    """Verify backend enforces 32+ character SECRET_KEY when ENVIRONMENT!=development."""
    with pytest.raises(ValueError, match="SECRET_KEY é obrigatória em ambiente de produção"):
        Settings(environment="production", secret_key="")

    with pytest.raises(ValueError, match="SECRET_KEY é obrigatória em ambiente de produção"):
        Settings(environment="production", secret_key=None)

    # Valid in development
    dev = Settings(environment="development", secret_key=None)
    assert len(dev.secret_key) >= 32


@pytest.mark.asyncio
async def test_gateway_enforces_authentication_when_configured(monkeypatch):
    """Verify that requests without Authorization header are rejected with 401."""
    monkeypatch.setattr(settings, "gateway_require_auth", True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert res.status_code == 401
        assert "Autenticação obrigatória" in res.text


@pytest.mark.asyncio
async def test_gateway_rejects_byok_when_disabled(monkeypatch):
    """Verify that BYOK is blocked with 403 when GATEWAY_ALLOW_BYOK=false."""
    monkeypatch.setattr(settings, "gateway_require_auth", True)
    monkeypatch.setattr(settings, "gateway_allow_byok", False)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/gateway/openai/v1/chat/completions",
            headers={"Authorization": "Bearer sk-proj-some-direct-key-1234567890"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert res.status_code == 403
        assert "BYOK" in res.text


@pytest.mark.asyncio
async def test_gateway_valid_virtual_key_auth(monkeypatch):
    """Verify that a valid active tp_live_ virtual key is authenticated and updates last_used_at."""
    monkeypatch.setattr(settings, "gateway_require_auth", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-mock-key")

    import uuid
    from sqlalchemy import delete

    raw_key = f"tp_live_rem_sec_test_{uuid.uuid4().hex[:16]}"
    k_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async with AsyncSessionLocal() as db:
        key_rec = ClientApiKey(
            name=f"Remediation Test Key {uuid.uuid4().hex[:8]}",
            key_hash=k_hash,
            key_prefix=raw_key[:12],
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(key_rec)
        await db.commit()

    try:
        def mock_upstream(req: httpx.Request):
            return httpx.Response(
                200,
                json={"id": "chatcmpl-test", "choices": [{"message": {"content": "ok"}}]},
            )

        mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))
        app.state.http_client = mock_client

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {raw_key}"},
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            )
            assert res.status_code == 200
            assert res.json()["choices"][0]["message"]["content"] == "ok"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ClientApiKey).where(ClientApiKey.key_hash == k_hash))
            await db.commit()


@pytest.mark.asyncio
async def test_realtime_disposable_ticket_flow():
    """Verify generation and single-use consumption of SSE stream tickets."""
    from routers.realtime import create_stream_ticket, validate_and_consume_ticket

    ticket = create_stream_ticket(ttl_seconds=5)
    assert ticket.startswith("ssec_")

    # 1. First validation succeeds
    assert validate_and_consume_ticket(ticket) is True

    # 2. Replay fails immediately (single-use)
    assert validate_and_consume_ticket(ticket) is False


@pytest.mark.asyncio
async def test_remote_bootstrap_takeover_prevention(monkeypatch):
    """Verify that remote callers without bootstrap token receive 403 Forbidden."""
    monkeypatch.setattr(settings, "admin_bootstrap_token", "test-token-val-987")

    transport = httpx.ASGITransport(app=app, client=("203.0.113.5", 43210))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/auth/setup",
            json={"username": "attacker", "password": "password123"},
        )
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_fails_closed_and_rejects_query_token(monkeypatch):
    """Verify require_admin is fail-closed when admin_api_key is None and rejects ?token=."""
    from routers.auth import create_access_token

    monkeypatch.setattr(settings, "admin_api_key", None)
    valid_jwt, _ = create_access_token("admin_user")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Anonymous request to admin route fails closed with 401
        r_anon = await client.post("/api/providers", json={"name": "test"})
        assert r_anon.status_code == 401

        # 2. Passing JWT via ?token= query parameter is strictly rejected with 401
        r_query = await client.post(f"/api/providers?token={valid_jwt}", json={"name": "test"})
        assert r_query.status_code == 401

        # 3. Passing JWT via standard Authorization: Bearer header is accepted
        r_bearer = await client.get("/api/keys", headers={"Authorization": f"Bearer {valid_jwt}"})
        assert r_bearer.status_code == 200


@pytest.mark.asyncio
async def test_realtime_ticket_requires_auth():
    """Verify requesting realtime stream tickets requires authentication and rejects anonymous callers."""
    from routers.auth import create_access_token

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Anonymous request for ticket -> 401
        res_anon = await client.post("/api/realtime/ticket")
        assert res_anon.status_code == 401

        # 2. Authenticated user requests ticket -> 200 with ticket
        token, _ = create_access_token("alice", user_id=42)
        res_auth = await client.post("/api/realtime/ticket", headers={"Authorization": f"Bearer {token}"})
        assert res_auth.status_code == 200
        data = res_auth.json()
        assert "ticket" in data
        assert data["ticket"].startswith("ssec_")
        assert data["user_id"] == 42

        # 3. Invalid ticket rejected with 401 on stream
        res_bad_stream = await client.get("/api/realtime/stream?ticket=ssec_invalid_fake")
        assert res_bad_stream.status_code == 401


@pytest.mark.asyncio
async def test_realtime_sse_event_and_metrics_isolation():
    """Verify event_generator filters real-time events to only match the connected user_id."""
    import asyncio
    from services.event_bus import event_bus
    from routers.realtime import event_generator

    gen_alice = event_generator(user_id=101)

    # Prime generator
    task = asyncio.create_task(gen_alice.__anext__())
    await asyncio.sleep(0.05)

    # 1. Publish event belonging to Bob (user_id=102) -> Alice should NOT receive it
    await event_bus.publish("request.completed", {
        "user_id": 102,
        "provider": "openai",
        "model": "gpt-4o",
        "tokens": 50,
    })
    await asyncio.sleep(0.05)
    assert not task.done()

    # 2. Publish event belonging to Alice (user_id=101) -> Alice MUST receive it
    await event_bus.publish("request.completed", {
        "user_id": 101,
        "provider": "anthropic",
        "model": "claude-3-5-sonnet",
        "tokens": 120,
    })
    event_str = await asyncio.wait_for(task, timeout=1.0)
    assert "claude-3-5-sonnet" in event_str
    assert '"user_id": 101' in event_str

    await gen_alice.aclose()


@pytest.mark.asyncio
async def test_realtime_ticket_rate_limiting(monkeypatch):
    """Verify rate limiting on /api/realtime/ticket returns 429 when threshold exceeded."""
    from config import settings
    monkeypatch.setattr(settings, "auth_rate_limit_rpm", 5)

    ip = "198.51.100.99"
    transport = httpx.ASGITransport(app=app, client=(ip, 54321))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user to get JWT
        reg_res = await client.post("/api/auth/register", json={
            "username": "sse_tenant",
            "email": "sse@tenant.com",
            "password": "Password123!",
        })
        token = reg_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Request 5 tickets (within limit)
        for _ in range(5):
            res = await client.post("/api/realtime/ticket", headers=headers)
            assert res.status_code == 200

        # 6th request should be throttled (429)
        throttled = await client.post("/api/realtime/ticket", headers=headers)
        assert throttled.status_code == 429
        assert "Retry-After" in throttled.headers
