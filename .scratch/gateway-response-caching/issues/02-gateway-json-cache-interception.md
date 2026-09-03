# 02: Gateway JSON Cache Interception, Bypass Headers and Telemetry

**What to build:**
Intercept inbound Gateway JSON requests before dispatching to upstream providers. On cache hit, return the stored response immediately in <5ms with $0.00 cost and inject headers `X-TokenPulse-Cache: HIT` and `X-TokenPulse-Cache-Age`. On cache miss, execute upstream request and asynchronously persist the response for subsequent calls. Respect `X-TokenPulse-Cache: false` and custom `X-TokenPulse-Cache-TTL`.

**Blocked by:** 01: Cache Model, Database Schema and Deterministic Hashing

**Status:** ready-for-agent

- [ ] Check cache prior to upstream execution in `_proxy_request`.
- [ ] Honor bypass headers (`X-TokenPulse-Cache: false`, `Cache-Control: no-cache`) and custom TTL (`X-TokenPulse-Cache-TTL`).
- [ ] On cache HIT, return stored response with HTTP headers `X-TokenPulse-Cache: HIT` and `X-TokenPulse-Cache-Age`, updating hit count.
- [ ] On cache MISS, forward request to upstream, and if status is 200, persist response to cache asynchronously with `X-TokenPulse-Cache: MISS`.
- [ ] Save telemetry in `RequestLog` tagging `cost_total = 0.00` and `cache_hit = True` for cache hits.
- [ ] Integration tests asserting HIT, MISS, bypass, and zero cost.
