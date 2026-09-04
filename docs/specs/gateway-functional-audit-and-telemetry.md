# Spec: Gateway Functional Audit and Real-Time Telemetry Hardening

## Problem Statement

While TokenPulse has undergone security hardening and release sanitation, its core capability as an **AI Observability Gateway** must be functionally proven under realistic, high-fidelity conditions. In production AI applications, gateways frequently suffer from silent edge-case failures: chunk buffering that destroys streaming interactivity (poor TTFT), orphaned connections during abrupt client disconnects, fabricated zero-token counts when providers omit usage metadata, status-code flattening (e.g., masking upstream 429/503 errors as generic 500s), duplicate log/SSE event emissions, and SQLite concurrency locks under parallel traffic. 

Developers and operators need absolute certainty that TokenPulse functions transparently: relaying provider responses faithfully, streaming tokens progressively with sub-millisecond overhead, measuring true Time-To-First-Token (TTFT), capturing granular telemetry without duplicates or data leaks, and pushing live events reliably to the dashboard via SSE.

## Solution

Conduct a comprehensive functional audit and hardening of the TokenPulse Gateway and Telemetry pipeline across 10 functional phases:
1. **Transparent Request Proxying**: Guarantee zero mutation of upstream payload structure, choices, finish reasons, or headers while faithfully recording latency, cost, and tokens.
2. **True Progressive Streaming & TTFT**: Enforce non-buffered chunk-by-chunk streaming using `time.perf_counter()` to record accurate `time_to_first_token_ms` and `stream_duration_ms`.
3. **Resilient Disconnect Handling**: Detect client aborts (`asyncio.CancelledError`), immediately close upstream HTTP connections (`upstream_resp.aclose()`), prevent orphaned async tasks, and record status `499` with `finish_reason = "cancelled"` without false success metrics.
4. **Strict Token Integrity & `usage_source`**: Differentiate reported vs unknown token usage. Add explicit schema column `usage_source` (`reported`, `unknown`), storing `None` (never `0`) when providers omit token metrics.
5. **Faithful Error Upstream Mapping**: Relay upstream HTTP 400, 401, 403, 429, 502, 503, 504 codes faithfully. Preserve `Retry-After` headers and sanitize sensitive credentials in error logs.
6. **SSE Single-Delivery & Deduplication**: Guarantee that each completed request dispatches exactly one `request.completed` event to the in-memory `EventBus` and SSE subscribers.
7. **Cache & Fallback Telemetry Coherence**: Ensure cache hits generate a single `RequestLog` entry marked `cache_hit = True` with `cost_total = 0.0`, while fallback executions record original and actual provider/model paths.
8. **Concurrency & SQLite Lock Verification**: Validate 25–50 concurrent requests against SQLite WAL mode to guarantee zero database locks, transaction rollbacks, or lost metrics.

## User Stories

1. As an AI application developer, I want my non-streaming requests through TokenPulse Gateway to return the exact response body, choices, tool calls, and status code from the provider, so that the Gateway acts as a fully transparent drop-in proxy.
2. As a frontend developer building chatbot interfaces, I want streaming responses (`stream=true`) to cede chunks progressively to the client as soon as they arrive from the upstream provider, so that my users never experience chunk buffering or degraded latency.
3. As an observability engineer, I want TokenPulse to record `time_to_first_token_ms` using high-resolution monotonic clocks (`time.perf_counter()`), so that I can accurately measure and alert on TTFT regressions across different LLM providers.
4. As an observability engineer, I want `stream_duration_ms` recorded consistently from stream start to the final token chunk, so that I have end-to-end visibility into stream throughput.
5. As a systems operator, I want the Gateway to immediately terminate upstream HTTP connections when a client disconnects prematurely, so that server resources and expensive upstream token generations are not wasted on orphaned requests.
6. As an auditor, I want client-aborted streams to be logged with HTTP status 499 and `finish_reason: "cancelled"`, so that client disconnects are never misclassified as successful completions or provider outages.
7. As an auditor, I want provider connection drops during streaming to record a failure state (e.g. 502 Bad Gateway), so that incomplete responses are never counted as successful requests.
8. As a data analyst, I want `input_tokens`, `output_tokens`, and `total_tokens` to be persisted as `None` (not `0`) when a provider omits usage data, so that averages and token analytics are not corrupted by artificial zero values.
9. As a data analyst, I want a dedicated `usage_source` column (`reported` vs `unknown`), so that downstream reporting can distinguish provider-metered tokens from unmetered calls.
10. As a financial administrator, I want model costs calculated strictly against the centralized pricing catalog, and recorded as `None` when a model is not in the catalog, so that unverified cost figures are never fabricated.
11. As a developer deploying a new or custom model, I want the Gateway to process and log the request normally even if the model is absent from the pricing catalog, so that novel models do not break proxy routing.
12. As an API client receiving rate limits (HTTP 429), I want the upstream `Retry-After` header preserved and passed through the Gateway, so that my application's exponential backoff logic functions correctly.
13. As an application developer encountering an upstream HTTP 400 Bad Request, I want the provider's exact error message returned to me, so that I can debug invalid prompts or parameters.
14. As a security officer, I want upstream HTTP 401 and 403 errors sanitized so that raw provider keys, headers, or internal tokens never leak in the response body or in server log files.
15. As a DevOps engineer, I want upstream HTTP 502, 503, and 504 gateway errors propagated with their native status codes rather than flattened into a generic 500 error, so that I know exactly which upstream failure occurred.
16. As an application developer, I want connection timeouts and read timeouts classified as `provider_timeout` in error telemetry, so that network timeouts are immediately distinguishable from API protocol errors.
17. As a dashboard user, I want every API request to have a unique correlation ID (`tp_req_...`), while preserving the provider's native ID (`provider_request_id`) separately in database records.
18. As an auditor, I want each API request to generate strictly one `RequestLog` record and one SSE event, so that metric counters, request counts, and cost aggregations are never duplicated.
19. As a dashboard operator, I want requests served from cache to record `cache_hit = true` and `cost_total = 0.0`, so that the dashboard accurately reflects provider cost savings without double-counting provider usage.
20. As a dashboard user monitoring the live UI, I want SSE connection status badges (`Live`, `Polling`, `Disconnected`) to reflect true network state, so that I am never shown a false `Live` indicator when SSE has failed.
21. As a dashboard user, I want metrics cards, graphs, and request tables to update reactively upon receiving `request.completed` SSE events without requiring a full browser page refresh.
22. As a platform engineer, I want 50 concurrent requests handled seamlessly without SQLite locking errors (`database is locked`), so that multi-threaded workloads do not drop telemetry under peak load.
23. As a developer making requests with virtual keys (`tp_live_...`), I want my requests authenticated before cache lookup or proxying, so that unauthorized callers cannot consume provider quota or access cached prompts.
24. As a performance engineer, I want the gateway proxy overhead (latency added by TokenPulse beyond upstream response time) to remain under 10ms for non-streaming requests, so that observability incurs no noticeable performance penalty.

## Implementation Decisions

1. **Schema Extension in `models.py`**:
   - Add `usage_source: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)` to `RequestLog`.
   - Supported values: `"reported"` (usage returned by provider payload), `"unknown"` (usage omitted by provider).
   - When usage is omitted, `input_tokens`, `output_tokens`, and `total_tokens` remain `None`, and `usage_source = "unknown"`.

2. **Stream Disconnect & Abort Semantics**:
   - Inside `stream_generator()` in `backend/routers/gateway.py`:
     - Catch `asyncio.CancelledError` on client disconnect.
     - Call `await upstream_resp.aclose()` immediately.
     - Record telemetry with `status_code = 499`, `finish_reason = "cancelled"`, and `error_msg = "Client disconnected during streaming"`.
     - Do not store aborted streams in the cache.
   - For upstream provider disconnects during streaming:
     - Catch network/stream read exceptions.
     - Record telemetry with `status_code = 502`, `finish_reason = "error"`, and sanitized exception text.

3. **HTTP Status Code and Header Preservation**:
   - Forward upstream status codes faithfully (400, 401, 403, 429, 502, 503, 504).
   - Explicitly preserve `Retry-After` header on 429 responses.
   - Classify timeouts explicitly: `error_msg = "provider_timeout"`.
   - Redact all sensitive tokens from error bodies using `redact_sensitive_text()`.

4. **SSE Event Delivery & Single-Delivery Guarantee**:
   - `_persist_gateway_telemetry` executes once in a background task per request.
   - On completion, `event_bus.publish("request.completed", event_data)` dispatches exactly one event to all active subscriber queues.
   - Cache hits dispatch one event with `cache_hit: True` and `tokens: cached_tokens`.

5. **Concurrency and SQLite Calibration**:
   - Retain SQLite in WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`).
   - Telemetry background writes use short-lived sessions (`async with AsyncSessionLocal() as db:`) to minimize transaction hold time.

## Testing Decisions

1. **High-Level Functional Behavioral Tests (`tests/test_functional_audit.py`)**:
   - All tests must interact via ASGI transport (`httpx.AsyncClient(transport=ASGITransport(app=app))`) with `httpx.MockTransport` for upstreams.
   - Zero tests will invoke real external paid APIs; mocks simulate non-streaming, streaming chunks, timeouts, disconnects, and error codes.
2. **Streaming Progressivity & TTFT Verification**:
   - Mock transport yields chunks with slight synthetic delays (`asyncio.sleep`).
   - Verify client receives chunks progressively and `time_to_first_token_ms` is strictly positive and matches monotonic elapsed time.
3. **Client Disconnect Simulation**:
   - Client starts streaming request and cancels its read task mid-stream (`task.cancel()`).
   - Verify `RequestLog` receives status 499, `finish_reason == "cancelled"`, and upstream transport receives closure signal.
4. **Concurrent Load Verification**:
   - Fire 30 concurrent requests using `asyncio.gather()`.
   - Verify exactly 30 unique `RequestLog` rows created, zero `database is locked` errors, and 100% status 200.
5. **SSE Single-Delivery Verification**:
   - Subscribe to `/api/realtime/stream` queue, trigger 1 gateway request, assert exactly 1 `request.completed` event received.

## Out of Scope

- Multi-tenant SaaS, billing engines, and Stripe integration.
- Database migration to PostgreSQL or Redis (deferred to P3).
- Kubernetes, Helm charts, or microservice decomposition.
- UI redesign or CSS overhaul.

## Further Notes

- The audit is purely functional: validating real correctness, streaming stability, telemetry integrity, and concurrency resilience on the current FastAPI + SQLite + Chart.js stack.
