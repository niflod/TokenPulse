"""
tests/test_tickets_features.py — Automated tests for tickets 01-05:
- Webhook alerts dispatching
- Gateway monthly budget cap blocking
- Virtual Client API Keys CRUD and gateway proxy validation
"""

import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import asyncio
import config
import httpx
import pytest
import pytest_asyncio
from database import AsyncSessionLocal, init_db
from main import app
from models import ClientApiKey, ProviderConfig, RequestLog
from routers.auth import create_access_token
from services.webhook import dispatch_alert_webhook
from sqlalchemy import delete, select


@pytest_asyncio.fixture(autouse=True)
async def setup_test_suite():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_webhook_alert_dispatch():
    """Verify that dispatch_alert_webhook sends structured payload to webhook URL."""
    captured_requests = []

    def mock_webhook_handler(request: httpx.Request):
        captured_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_webhook_handler))

    alert_payload = {
        "metric": "error_rate",
        "severity": "critical",
        "currentValue": 12.5,
        "threshold": 5.0,
        "message": "Taxa de erro anormal",
        "provider": "openai",
    }

    success = await dispatch_alert_webhook(
        alert=alert_payload,
        custom_url="https://discord.com/api/webhooks/mock_test_123",
        client=mock_client,
    )
    assert success is True
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert "discord.com" in str(req.url)
    import json
    data = json.loads(req.content.decode("utf-8"))
    assert data["event"] == "tokenpulse.alert"
    assert "error_rate" in data["content"]
    await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_monthly_budget_cap():
    """Verify that exceeding provider monthly budget blocks further gateway calls with 429."""
    import config
    import routers.gateway as gw

    # Set mock budget of $0.05
    old_budget = config.settings.provider_monthly_budget
    config.settings.provider_monthly_budget = 0.05

    try:
        # Seed a RequestLog with cost exceeding $0.05
        async with AsyncSessionLocal() as db:
            from datetime import datetime, timezone
            db.add(RequestLog(
                provider="gemini",
                model="gemini-1.5-flash",
                timestamp=datetime.now(timezone.utc),
                cost_total=0.10,
                status_code=200,
            ))
            await db.commit()

        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/gemini/v1beta/models",
                json={},
                headers={"Authorization": "Bearer mock-gemini-key"},
            )
            assert res.status_code == 429
            assert "Orçamento mensal do provedor 'gemini' excedido" in res.json()["detail"]
    finally:
        config.settings.provider_monthly_budget = old_budget


@pytest.mark.asyncio
async def test_virtual_client_api_keys_flow():
    """Verify issuing, using, toggling, and revoking TokenPulse virtual API keys."""
    token, _ = create_access_token("admin")
    auth_headers = {"Authorization": f"Bearer {token}"}

    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
        # 1. Create client key
        res = await client.post(
            "/api/keys",
            json={"name": "Frontend Web App", "rate_limit_rpm": 100},
            headers=auth_headers,
        )
        assert res.status_code == 201
        key_data = res.json()
        assert "tp_live_" in key_data["api_key"]
        raw_virtual_key = key_data["api_key"]
        key_id = key_data["id"]

        # 2. List keys
        list_res = await client.get("/api/keys", headers=auth_headers)
        assert list_res.status_code == 200
        assert any(k["id"] == key_id for k in list_res.json())

        # 3. Use virtual key in Gateway
        fake_upstream = {"id": "chatcmpl-test", "choices": [{"message": {"role": "assistant", "content": "Ok"}}]}
        mock_http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=fake_upstream)))
        app.state.http_client = mock_http

        try:
            # Seed provider config in DB so virtual key resolves upstream key
            from models import ProviderConfig
            async with AsyncSessionLocal() as db:
                secret = config.settings.get_fernet_key()
                enc_key = ProviderConfig.encrypt_key("sk-upstream-secret-999", secret)
                p_stmt = select(ProviderConfig).where(ProviderConfig.name == "openai")
                p_curr = (await db.execute(p_stmt)).scalar_one_or_none()
                if p_curr:
                    p_curr.api_key_encrypted = enc_key
                    p_curr.enabled = True
                else:
                    db.add(ProviderConfig(name="openai", display_name="OpenAI Prod", api_key_encrypted=enc_key, enabled=True))
                await db.commit()

            gw_res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]},
                headers={"Authorization": f"Bearer {raw_virtual_key}"},
            )
            assert gw_res.status_code == 200
            assert "x-tokenpulse-request-id" in gw_res.headers
        finally:
            await mock_http.aclose()

        # 4. Toggle key off
        toggle_res = await client.put(f"/api/keys/{key_id}/toggle", headers=auth_headers)
        assert toggle_res.status_code == 200
        assert toggle_res.json()["enabled"] is False

        # 5. Using disabled key returns 401
        gw_disabled = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o-mini"},
            headers={"Authorization": f"Bearer {raw_virtual_key}"},
        )
        assert gw_disabled.status_code == 401
        assert "desabilitada" in gw_disabled.json()["detail"]

        # 6. Delete key
        del_res = await client.delete(f"/api/keys/{key_id}", headers=auth_headers)
        assert del_res.status_code == 204
