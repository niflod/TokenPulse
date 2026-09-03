# 02: Gateway Failover Engine for 429, 5xx, and Timeouts

**What to build:** Resilient proxy execution inside TokenPulse Gateway that catches upstream HTTP 429, 5xx errors, or connection timeouts and automatically rewrites the payload to retry against the next configured fallback target model without returning an error to the client.

**Blocked by:** 01: Fallback Rules Model and CRUD.

**Status:** ready-for-agent

- [ ] Helper function in `gateway.py` queries active fallback rules for the requested provider and model ordered by priority.
- [ ] Upstream request wrapper intercepts status codes (429, 500, 502, 503, 504) and `httpx.TimeoutException`.
- [ ] Request body JSON rewritten with target model name, upstream base URL adjusted to target provider, and target provider credentials injected.
- [ ] Streaming requests (SSE) support failover if error occurs before token stream begins.
- [ ] Automated tests mocking upstream failures and verifying successful rerouting to Groq/Mistral fallback targets.
