"""
tests/test_gateway.py — Comprehensive tests for TokenPulse Gateway, Streaming, TTFT, and Telemetry.
Uses httpx.MockTransport to ensure zero external calls.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import httpx
import pytest
from database import AsyncSessionLocal, init_db
from main import app
from models import RequestLog
from sqlalchemy import select


import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    yield


@pytest.mark.asyncio
async def test_gateway_health():
    """Verify gateway health check returns supported providers."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/gateway/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "openai" in data["supported_providers"]
        assert "anthropic" in data["supported_providers"]
        assert "gemini" in data["supported_providers"]


@pytest.mark.asyncio
async def test_gateway_openai_non_streaming():
    """Verify transparent proxy, token extraction, cost calculation, and telemetry persistence."""
    fake_upstream_response = {
        "id": "chatcmpl-mock-12345",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello world from mocked OpenAI!"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1500,
            "completion_tokens": 600,
            "total_tokens": 2100,
            "prompt_tokens_details": {"cached_tokens": 500},
            "completion_tokens_details": {"reasoning_tokens": 100},
        },
    }

    def mock_handler(request: httpx.Request):
        assert "api.openai.com" in str(request.url)
        assert request.headers.get("authorization") == "Bearer sk-custom-test-key"
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json", "x-request-id": "req_openai_mock_99"},
            content=json.dumps(fake_upstream_response).encode("utf-8"),
        )

    # Inject mock client into app.state
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            payload = {
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "Hello"}],
            }
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer sk-custom-test-key"},
            )

            assert res.status_code == 200
            assert "X-TokenPulse-Request-Id" in res.headers
            body = res.json()
            assert body["id"] == "chatcmpl-mock-12345"
            assert body["choices"][0]["message"]["content"] == "Hello world from mocked OpenAI!"

            # Allow async task to commit telemetry
            await asyncio.sleep(0.1)

            # Query database to confirm RequestLog was saved with metrics and cost
            async with AsyncSessionLocal() as db:
                stmt = select(RequestLog).order_by(RequestLog.id.desc())
                log_entry = (await db.execute(stmt)).scalars().first()
                assert log_entry is not None
                assert log_entry.provider == "openai"
                assert log_entry.model == "gpt-4o"
                assert log_entry.input_tokens == 1500
                assert log_entry.output_tokens == 600
                assert log_entry.total_tokens == 2100
                assert log_entry.cached_input_tokens == 500
                assert log_entry.reasoning_tokens == 100
                assert log_entry.finish_reason == "stop"
                assert log_entry.cost_total is not None
                assert log_entry.cost_total > 0
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_openai_streaming_ttft():
    """Verify that SSE streaming delivers chunks progressivelly and calculates TTFT."""
    sse_chunks = [
        b'data: {"id":"chatcmpl-stream-1","choices":[{"delta":{"content":"Hi"}}]}\n\n',
        b'data: {"id":"chatcmpl-stream-1","choices":[{"delta":{"content":" there!"}}]}\n\n',
        b'data: {"id":"chatcmpl-stream-1","choices":[{"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}\n\n',
        b'data: [DONE]\n\n',
    ]

    async def stream_body():
        for chunk in sse_chunks:
            await asyncio.sleep(0.01)
            yield chunk

    def mock_stream_handler(request: httpx.Request):
        return httpx.Response(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            content=stream_body(),
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_stream_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            payload = {
                "model": "gpt-4o-mini",
                "stream": True,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer sk-stream-test-key"},
            )

            assert res.status_code == 200
            assert "text/event-stream" in res.headers["content-type"]
            text_received = res.text
            assert "Hi" in text_received
            assert "there!" in text_received
            assert "[DONE]" in text_received

            # Allow async task to commit telemetry
            await asyncio.sleep(0.1)

            async with AsyncSessionLocal() as db:
                stmt = select(RequestLog).where(RequestLog.model == "gpt-4o-mini").order_by(RequestLog.id.desc())
                log_entry = (await db.execute(stmt)).scalars().first()
                assert log_entry is not None
                assert log_entry.provider == "openai"
                assert log_entry.time_to_first_token_ms is not None
                assert log_entry.time_to_first_token_ms > 0
                assert log_entry.stream_duration_ms is not None
                assert log_entry.stream_duration_ms >= log_entry.time_to_first_token_ms
                assert log_entry.total_tokens == 15
                assert log_entry.finish_reason == "stop"
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_error_and_secret_redaction():
    """Verify upstream errors (e.g. 429 Rate Limit) are forwarded and secrets redacted from error_message."""
    secret_leaked_response = {
        "error": {
            "message": "Rate limit exceeded for key sk-1234567890abcdef1234567890abcdef. Please retry in 20s.",
            "type": "insufficient_quota",
        }
    }

    def mock_error_handler(request: httpx.Request):
        return httpx.Response(
            status_code=429,
            headers={"content-type": "application/json"},
            content=json.dumps(secret_leaked_response).encode("utf-8"),
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_error_handler))
    app.state.http_client = mock_client

    try:
        asgi_transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o"},
                headers={"Authorization": "Bearer sk-mock-error-key"},
            )

            assert res.status_code == 429

            await asyncio.sleep(0.1)

            async with AsyncSessionLocal() as db:
                stmt = select(RequestLog).where(RequestLog.status_code == 429).order_by(RequestLog.id.desc())
                log_entry = (await db.execute(stmt)).scalars().first()
                assert log_entry is not None
                assert log_entry.error_message is not None
                # Assert secret was redacted and is NOT in the database!
                assert "sk-1234567890abcdef1234567890abcdef" not in log_entry.error_message
                assert "[REDACTED]" in log_entry.error_message
    finally:
        await mock_client.aclose()


@pytest.mark.asyncio
async def test_gateway_unsupported_provider():
    """Verify calling an unknown provider returns 400 Bad Request."""
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
        res = await client.post("/gateway/unknown_llm/v1/completions", json={})
        assert res.status_code == 400
        assert "não suportado" in res.json()["detail"]


@pytest.mark.asyncio
async def test_models_listing_and_detail():
    """Verify models endpoint returns list of models and details correctly."""
    asgi_transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi_transport, base_url="http://test") as client:
        # 1. Models list
        res = await client.get("/api/models")
        assert res.status_code == 200
        models_data = res.json()
        assert isinstance(models_data, list)

        # 2. Model detail
        detail_res = await client.get("/api/models/openai/gpt-4o")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["model"] == "gpt-4o"
        assert "overview" in detail
        assert "usage" in detail
        assert "performance" in detail

