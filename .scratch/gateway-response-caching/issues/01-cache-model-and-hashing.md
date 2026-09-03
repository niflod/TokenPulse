# 01: Cache Model, Database Schema and Deterministic Hashing

**What to build:**
Create the persistent SQLite storage table and deterministic hashing utility for Gateway request payloads. Requests with equivalent parameters (provider, model, messages, temperature, tools) generate identical SHA-256 keys, supporting storage, retrieval, and automated TTL expiration.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] SQLAlchemy ORM model `GatewayResponseCache` with fields for cache key, provider, model, response JSON, token counts, estimated saved cost, timestamps, and hit count.
- [ ] Database initialization and automatic table migration for `gateway_response_cache` with an index on `expires_at`.
- [ ] Canonical hashing function that sorts dictionary keys and serializes semantic request attributes (provider, model, messages, temperature, tools).
- [ ] Automated tests validating hash determinism, cache write/read operations, and expiration filtering.
