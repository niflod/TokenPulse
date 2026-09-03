# 04: Cache Management REST API (Stats, Flush, Configuration)

**What to build:**
Create administrative REST endpoints under `/api/cache` to query performance statistics (total items cached, hit rate, total cost saved), flush the cache database, and dynamically configure the default TTL and global enabled status.

**Blocked by:** 01: Cache Model, Database Schema and Deterministic Hashing

**Status:** ready-for-agent

- [ ] `GET /api/cache/stats`: Aggregate cache hits, misses, total saved dollars, and current entry count.
- [ ] `POST /api/cache/flush`: Invalidate all stored cache entries (protected by admin authentication).
- [ ] `PUT /api/cache/config`: Update global caching enabled flag and default TTL.
- [ ] Automated tests covering all management endpoints and authorization rules.
