# 01: Fallback Rules Model and CRUD

**What to build:** Administrator endpoints to manage model fallback configurations, allowing users to define ordered failover chains (e.g. gpt-4o -> Groq llama-3.3-70b -> Mistral mistral-large) with database persistence and sensible defaults seeded at startup.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `FallbackRule` ORM model created with `source_provider`, `source_model`, `target_provider`, `target_model`, `priority`, and `enabled` flag.
- [ ] Database migration helper in `database.py` creates table and seeds default rules if table is empty.
- [ ] CRUD REST endpoints at `/api/fallback-rules` protected by JWT/admin auth.
- [ ] Automated unit tests verifying rule creation, prioritization order, toggling, and deletion.
