# 03: Budget Cap Failover

**What to build:** Seamless failover when a provider reaches its monthly budget cap (`provider_monthly_budget`), rerouting incoming requests immediately to alternative providers (such as cheaper or local models) instead of hard-rejecting with HTTP 429.

**Blocked by:** 02: Gateway Failover Engine for 429, 5xx, and Timeouts.

**Status:** ready-for-agent

- [ ] `_check_provider_budget` returns a boolean indicating budget exhaustion.
- [ ] If primary provider's monthly budget is exceeded, Gateway looks up active fallback rules and reroutes directly to the first available target whose budget is not exceeded.
- [ ] Fallback reason tagged as `budget_cap`.
- [ ] If all fallback targets exceed budget, return HTTP 429 with clear error explanation.
- [ ] Automated tests asserting that budget-capped requests failover gracefully.
