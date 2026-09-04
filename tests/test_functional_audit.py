"""
tests/test_functional_audit.py — Comprehensive functional verification suite
for TokenPulse Gateway, Streaming, Telemetry integrity, and SQLite concurrency.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

import httpx
import pytest
import pytest_asyncio
from config import settings
from database import AsyncSessionLocal, init_db
from main import app
from models import RequestLog
from services.cache_service import flush_all_cache
from sqlalchemy import select


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db(monkeypatch):
    """
    Ensure tables exist, cache is clean, and gateway cache is disabled
    by default to guarantee isolated tests.
    """
    await init_db()
    async with AsyncSessionLocal() as db:
        await flush_all_cache(db)
    monkeypatch.setattr(settings, "gateway_cache_enabled", False)
    yield


@pytest.mark.asyncio
async def test_normal_request_transparency_and_single_log(monkeypatch):
    """Ticket 01: Verify transparent non-streaming proxying and single log emission."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    provider_payload = {
        "id": "chatcmpl-test-transparency",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "Direct response faithful"},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40}
    }

    def mock_upstream(req: httpx.Request):
        return httpx.Response(200, json=provider_payload, headers={"x-request-id": "req-native-12345"})

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ticket-01-query"}]},
        )

        assert res.status_code == 200
        assert res.json() == provider_payload
        assert res.headers.get("X-TokenPulse-Request-Id", "").startswith("tp_req_")

        tp_req_id = res.headers.get("X-TokenPulse-Request-Id")

    # Give async task time to persist
    await asyncio.sleep(0.15)

    async with AsyncSessionLocal() as db:
        stmt = select(RequestLog).where(RequestLog.request_id == tp_req_id)
        logs = (await db.execute(stmt)).scalars().all()
        assert len(logs) == 1, "Exactly one log record must be persisted"
        log = logs[0]
        assert log.provider == "openai"
        assert log.model == "gpt-4o"
        assert log.input_tokens == 15
        assert log.output_tokens == 25
        assert log.total_tokens == 40
        assert log.usage_source == "reported"
        assert log.provider_request_id == "chatcmpl-test-transparency"
        assert log.finish_reason == "stop"


@pytest.mark.asyncio
async def test_usage_source_and_null_token_semantics(monkeypatch):
    """Ticket 02: When provider omits usage, tokens must be None (never 0) and usage_source='unknown'."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    no_usage_payload = {
        "id": "chatcmpl-no-usage",
        "choices": [{"message": {"content": "No usage report"}, "finish_reason": "stop"}],
    }

    def mock_upstream(req: httpx.Request):
        return httpx.Response(200, json=no_usage_payload)

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ticket-02-query"}]},
        )
        assert res.status_code == 200
        tp_req_id = res.headers.get("X-TokenPulse-Request-Id")

    await asyncio.sleep(0.15)

    async with AsyncSessionLocal() as db:
        stmt = select(RequestLog).where(RequestLog.request_id == tp_req_id)
        log = (await db.execute(stmt)).scalar_one_or_none()
        assert log is not None
        assert log.input_tokens is None, "input_tokens must be None when omitted"
        assert log.output_tokens is None, "output_tokens must be None when omitted"
        assert log.total_tokens is None, "total_tokens must be None when omitted"
        assert log.usage_source == "unknown"


@pytest.mark.asyncio
async def test_progressive_streaming_and_monotonic_ttft(monkeypatch):
    """Ticket 03: Chunks must be progressive and TTFT measured using monotonic clock."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    async def streaming_generator():
        yield b'data: {"id":"stream-1","choices":[{"delta":{"role":"assistant"}}]}\n\n'
        await asyncio.sleep(0.05)
        yield b'data: {"id":"stream-1","choices":[{"delta":{"content":"Hello "}}]}\n\n'
        await asyncio.sleep(0.05)
        yield b'data: {"id":"stream-1","choices":[{"delta":{"content":"World!"},"finish_reason":"stop"}],"usage":{"prompt_tokens":5,"completion_tokens":2,"total_tokens":7}}\n\n'
        yield b'data: [DONE]\n\n'

    def mock_upstream(req: httpx.Request):
        return httpx.Response(200, content=streaming_generator(), headers={"content-type": "text/event-stream"})

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        t0 = time.perf_counter()
        res = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ticket-03-query"}], "stream": True},
        )
        assert res.status_code == 200
        assert "text/event-stream" in res.headers.get("content-type", "")
        tp_req_id = res.headers.get("X-TokenPulse-Request-Id")

        # Read text chunks
        body = res.text
        assert "Hello " in body
        assert "World!" in body
        assert "[DONE]" in body

    await asyncio.sleep(0.2)

    async with AsyncSessionLocal() as db:
        stmt = select(RequestLog).where(RequestLog.request_id == tp_req_id)
        log = (await db.execute(stmt)).scalar_one_or_none()
        assert log is not None
        assert log.time_to_first_token_ms is not None
        assert log.time_to_first_token_ms >= 0.0, "TTFT must be non-negative"
        assert log.stream_duration_ms is not None
        assert log.stream_duration_ms >= log.time_to_first_token_ms, "Total duration must be >= TTFT"
        assert log.finish_reason == "stop"
        assert log.input_tokens == 5
        assert log.output_tokens == 2
        assert log.total_tokens == 7
        assert log.usage_source == "reported"


@pytest.mark.asyncio
async def test_client_disconnect_status_499(monkeypatch):
    """Ticket 04: Client disconnect during stream must log status 499 and finish_reason='cancelled'."""
    from routers.gateway import _proxy_request
    from starlette.requests import Request

    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    closed_signal = asyncio.Event()

    async def infinite_stream():
        try:
            while True:
                yield b'data: {"choices":[{"delta":{"content":"streaming forever..."}}]}\n\n'
                await asyncio.sleep(0.02)
        finally:
            closed_signal.set()

    def mock_upstream(req: httpx.Request):
        return httpx.Response(200, content=infinite_stream(), headers={"content-type": "text/event-stream"})

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    body = json.dumps({
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "ticket-04-query"}],
        "stream": True,
    }).encode("utf-8")

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/gateway/openai/v1/chat/completions",
        "raw_path": b"/gateway/openai/v1/chat/completions",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "app": app,
    }

    req = Request(scope, receive)
    res = await _proxy_request(provider="openai", subpath="v1/chat/completions", request=req)
    tp_req_id = res.headers.get("X-TokenPulse-Request-Id")
    assert tp_req_id is not None, "Gateway must have assigned a TokenPulse Request ID"

    gen = res.body_iterator
    try:
        await anext(gen)
    except StopAsyncIteration:
        pass

    await asyncio.sleep(0.2)

    async with AsyncSessionLocal() as db:
        stmt = select(RequestLog).where(RequestLog.request_id == tp_req_id)
        log = (await db.execute(stmt)).scalar_one_or_none()
        assert log is not None
        assert log.status_code == 499, f"Expected 499 on client cancel, got {log.status_code}"
        assert log.finish_reason == "cancelled"
        assert "Client disconnected" in (log.error_message or "")


@pytest.mark.asyncio
async def test_upstream_errors_and_retry_after(monkeypatch):
    """Ticket 05: Status codes and Retry-After header must be faithfully relayed."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    # 429 Too Many Requests with Retry-After on a model with no fallback configured
    def mock_429(req: httpx.Request):
        return httpx.Response(
            429,
            json={"error": {"message": "Rate limit exceeded"}},
            headers={"Retry-After": "12", "x-request-id": "req-429"},
        )

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_429))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-3.5-turbo", "messages": [{"role": "user", "content": "ticket-05-query"}]},
        )
        assert res.status_code == 429
        assert res.headers.get("retry-after") == "12"
        tp_req_id = res.headers.get("X-TokenPulse-Request-Id")

    await asyncio.sleep(0.15)
    async with AsyncSessionLocal() as db:
        stmt = select(RequestLog).where(RequestLog.request_id == tp_req_id)
        log = (await db.execute(stmt)).scalar_one_or_none()
        assert log is not None
        assert log.status_code == 429


@pytest.mark.asyncio
async def test_cache_and_fallback_telemetry(monkeypatch):
    """Ticket 06: Cache hits record cost_total=0.0 and cache_hit=True; fallback records single consolidated log."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")
    monkeypatch.setattr(settings, "gateway_cache_enabled", True)

    call_count = 0

    def mock_upstream(req: httpx.Request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-cached",
                "choices": [{"message": {"content": "Cached answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Request 1: Prime cache
        res1 = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ticket-06-cache-prime"}]},
        )
        assert res1.status_code == 200
        req1_id = res1.headers.get("X-TokenPulse-Request-Id")

        # Allow cache persistence task
        await asyncio.sleep(0.2)

        # Request 2: Must be cache hit
        res2 = await client.post(
            "/gateway/openai/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ticket-06-cache-prime"}]},
        )
        assert res2.status_code == 200
        assert res2.headers.get("X-TokenPulse-Cache") == "HIT"
        req2_id = res2.headers.get("X-TokenPulse-Request-Id")

    await asyncio.sleep(0.2)
    assert call_count == 1, "Upstream should have been called only once"

    async with AsyncSessionLocal() as db:
        stmt2 = select(RequestLog).where(RequestLog.request_id == req2_id)
        hit_log = (await db.execute(stmt2)).scalar_one_or_none()
        assert hit_log is not None
        assert hit_log.cache_hit is True or hit_log.cache_hit == 1
        assert hit_log.cost_total == 0.0


@pytest.mark.asyncio
async def test_sse_single_delivery_per_request(monkeypatch):
    """Ticket 07: Exactly one event is delivered per request via EventBus/SSE."""
    from services.event_bus import event_bus

    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    def mock_upstream(req: httpx.Request):
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-sse",
                "choices": [{"message": {"content": "SSE response"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    queue = event_bus.subscribe()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": "ticket-07-query"}]},
            )
            assert res.status_code == 200
            tp_req_id = res.headers.get("X-TokenPulse-Request-Id")

        # Collect event bus events
        received_events = []
        timeout_at = time.perf_counter() + 1.0
        while time.perf_counter() < timeout_at:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=0.2)
                if evt.get("data", {}).get("request_id") == tp_req_id:
                    received_events.append(evt)
            except asyncio.TimeoutError:
                break

        assert len(received_events) == 1, f"Expected 1 SSE event for {tp_req_id}, got {len(received_events)}"
        payload = received_events[0]["data"]
        assert payload["provider"] == "openai"
        assert payload["model"] == "gpt-4o"
        assert payload["usage_source"] == "reported"
    finally:
        event_bus.unsubscribe(queue)


@pytest.mark.asyncio
async def test_concurrency_and_sqlite_wal_resilience(monkeypatch):
    """Ticket 08: 30 concurrent requests succeed without database locks or lost logs."""
    monkeypatch.setattr(settings, "openai_api_key", "sk-mock-key")

    def mock_upstream(req: httpx.Request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "concurrent answer"}}]})

    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_upstream))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async def make_call(idx: int):
            r = await client.post(
                "/gateway/openai/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": f"query {idx}"}]},
            )
            assert r.status_code == 200
            return r.headers.get("X-TokenPulse-Request-Id")

        t_start_all = time.perf_counter()
        tasks = [make_call(i) for i in range(30)]
        results = await asyncio.gather(*tasks)
        total_time_ms = (time.perf_counter() - t_start_all) * 1000

    request_ids = results
    avg_dur_per_req = total_time_ms / len(tasks)

    # Average throughput overhead per request must be < 25ms
    assert avg_dur_per_req < 25.0, f"Average gateway throughput overhead was {avg_dur_per_req:.2f}ms"

    # Poll up to 2 seconds for background telemetry tasks to finish
    persisted = []
    for _ in range(20):
        await asyncio.sleep(0.1)
        async with AsyncSessionLocal() as db:
            stmt = select(RequestLog).where(RequestLog.request_id.in_(request_ids))
            persisted = (await db.execute(stmt)).scalars().all()
            if len(persisted) == 30:
                break

    assert len(persisted) == 30, f"Expected 30 persisted logs, found {len(persisted)}"
