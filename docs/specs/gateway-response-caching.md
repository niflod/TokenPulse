# Spec: Gateway Response Caching and Cost Reduction

## Problem Statement

Applications interacting with LLMs frequently submit repetitive prompts—such as common user queries, system health checks, classification workflows, and deterministic extraction tasks. Each duplicate request currently hits the upstream provider (e.g. OpenAI, Anthropic), incurring full financial cost and multi-second latency (500ms–3000ms+), consuming rate-limit tokens (TPM/RPM), and risking transient provider failures. Developers lack a simple, zero-maintenance mechanism to eliminate these redundant costs and speed up repeated requests without building external caching systems.

## Solution

TokenPulse Gateway will introduce an integrated Response Caching engine backed by SQLite. Identical requests will be matched using a deterministic cryptographic hash (SHA-256) of the normalized request components (provider, model, prompt messages, temperature, and tool definitions). On a cache hit, the Gateway immediately returns the stored response in <5ms at $0.00 cost, with full support for both standard JSON payloads and reconstructed SSE streaming. The system provides global activation with configurable TTL, per-request client overrides (`X-TokenPulse-Cache`), full telemetry with cost savings tracking, and an admin UI to monitor efficiency and flush the cache.

## User Stories

1. As an application developer, I want identical LLM requests to be answered from cache in <5ms, so that my end users experience near-instantaneous responses.
2. As a FinOps administrator, I want repeated queries to cost $0.00 in upstream API spend, so that the organization's LLM budget is optimized without degrading functionality.
3. As an application developer, I want to bypass the cache when needed by sending `X-TokenPulse-Cache: false` or `no-cache`, so that dynamic or non-deterministic workflows always hit the live model.
4. As an application developer, I want to specify custom TTLs per request via `X-TokenPulse-Cache-TTL: <seconds>`, so that high-frequency data can expire faster or slower than default rules.
5. As a client consumer using streaming (`stream: true`), I want cached responses to be streamed back seamlessly via Server-Sent Events (SSE), so that UI chat streaming works identically without client-side code changes.
6. As a developer inspecting HTTP responses, I want `X-TokenPulse-Cache: HIT` (or `MISS`) and `X-TokenPulse-Cache-Age: <seconds>` headers, so that my client code knows whether a response was fresh or cached.
7. As a dashboard administrator, I want to toggle response caching globally and configure the default TTL (e.g. 3600 seconds) in the dashboard settings, so that I have centralized policy control.
8. As a dashboard administrator, I want a "Limpar Cache" (Flush Cache) button in the Settings interface, so that I can immediately invalidate all stored responses when model prompts or business rules change.
9. As a dashboard operator, I want to see a visual `⚡ Cache HIT` badge and $0.00 cost in the Request Log table, so that I can audit which queries benefited from caching.
10. As a FinOps administrator, I want to see a "Total Economizado por Cache" (Total Saved) metric and "Cache Hit Rate" percentage on the dashboard, so that I can report the tangible ROI of TokenPulse.

## Implementation Decisions

1. **Storage and Schema (`gateway_response_cache`)**:
   - Store cache entries in a dedicated SQLite table: `gateway_response_cache` with columns:
     - `cache_key`: `VARCHAR(64)` PRIMARY KEY (SHA-256 hex digest)
     - `provider`: `VARCHAR(50)`
     - `model`: `VARCHAR(100)`
     - `response_json`: `TEXT` (complete upstream response payload)
     - `response_headers_json`: `TEXT` (sanitized upstream headers like content-type)
     - `input_tokens`: `INTEGER`
     - `output_tokens`: `INTEGER`
     - `total_tokens`: `INTEGER`
     - `estimated_saved_cost`: `FLOAT` (what the query would have costed if sent upstream)
     - `created_at`: `DATETIME`
     - `expires_at`: `DATETIME` (indexed for high-performance eviction and queries)
     - `hit_count`: `INTEGER` DEFAULT 0
   - Implement automatic background eviction of expired rows during reads and via scheduled cleanups.

2. **Deterministic Cache Key Generation**:
   - Normalize the request payload before hashing:
     - Sort JSON keys of the body.
     - Extract relevant semantic parameters: `provider`, `model`, `messages` (or `prompt`), `temperature`, `top_p`, `tools`, `tool_choice`.
     - Exclude transient flags like `stream` from the key itself, allowing a streaming request to hit a cached non-streaming response and vice-versa.
   - Compute SHA-256 over `f"{provider}:{model}:{canonical_json}"`.

3. **Gateway Interception Seam**:
   - In `_proxy_request`, before initiating upstream provider calls or failover loops:
     - Check if global caching is enabled in settings.
     - Check if client passed `X-TokenPulse-Cache: false` or `Cache-Control: no-cache`. If so, skip cache lookup.
     - Look up `cache_key` in `gateway_response_cache` where `expires_at > now()`.
     - On Cache HIT:
       - Increment `hit_count` in DB.
       - If `stream: false`, return JSON `Response` with `X-TokenPulse-Cache: HIT` and `X-TokenPulse-Cache-Age`.
       - If `stream: true`, synthesize SSE chunks from the cached response with realistic chunking and finish reasons.
       - Log telemetry with `status_code=200`, `cost_total=0.00`, `cache_hit=True`, `latency_ms` (<5ms), and broadcast to the SSE realtime stream.
     - On Cache MISS:
       - Proceed with normal upstream execution (and failover if applicable).
       - When upstream returns HTTP 200, asynchronously store response in `gateway_response_cache` with calculated TTL.

4. **Cache Management API**:
   - Provide endpoints:
     - `GET /api/cache/stats`: returns total entries, cache hit rate, total estimated dollars saved.
     - `POST /api/cache/flush`: deletes all cached entries, protected by admin auth.
     - `PUT /api/cache/config`: update default TTL and global enabled status.

5. **Dashboard UI Integration**:
   - Add mini-card / stat on Dashboard: "Economia com Cache" ($ e taxa de acerto %).
   - Add Cache Management Card in Settings: toggle status, default TTL input, and "Esvaziar Cache" button.
   - Render `⚡ Cache HIT` badge on Request Logs table.

## Testing Decisions

1. **Behavioral Black-Box Tests**:
   - Test that the first request produces a `MISS` (calls upstream mock) and caches the response.
   - Test that an identical second request produces a `HIT` (does NOT call upstream mock), returns in <10ms, has `X-TokenPulse-Cache: HIT`, and logs `cost_total = 0.0`.
   - Test that `X-TokenPulse-Cache: false` forces a live upstream call even if a cache entry exists.
   - Test that custom `X-TokenPulse-Cache-TTL` overrides default TTL.
   - Test that expired cache entries are not served and get refreshed.
   - Test that streaming requests (`stream: true`) correctly receive SSE chunks generated from cached entries.
   - Test that calling `POST /api/cache/flush` clears the cache and the next request hits upstream again.
2. **Prior Art in Codebase**:
   - Follow patterns established in `tests/test_fallback.py` and `tests/test_gateway.py` using `httpx.ASGITransport` and `httpx.MockTransport`.

## Out of Scope

- Semantic embeddings-based approximate vector caching (only exact deterministic hash matching is in scope for v1).
- Distributed Redis caching (single-node SQLite is sufficient for TokenPulse's embedded architecture).
- Caching for non-200 HTTP responses.

## Further Notes

- In accordance with Karpathy guidelines and Ponytail philosophy, using SQLite with index on `expires_at` keeps the architecture self-contained with zero new external dependencies or operational overhead.
