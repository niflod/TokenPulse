# 04: Telemetry, Response Headers, and Audit Tracking

**What to build:** Transparent visibility for failover events through HTTP response headers and database telemetry fields, enabling consumers to inspect fallback metadata and administrators to audit rerouted executions with correct cost accounting.

**Blocked by:** 02: Gateway Failover Engine for 429, 5xx, and Timeouts.

**Status:** ready-for-agent

- [ ] Add columns to `RequestLog`: `fallback_triggered` (bool), `original_provider` (str), `original_model` (str), and `fallback_reason` (str).
- [ ] Database migration helper in `database.py` adds new columns via dynamic `ALTER TABLE`.
- [ ] Injected HTTP headers on successful fallback responses (`X-TokenPulse-Fallback: true`, `X-TokenPulse-Original-Model`, `X-TokenPulse-Actual-Model`, `X-TokenPulse-Fallback-Reason`).
- [ ] Telemetry persistence records both original and actual targets, calculating token costs based on the model actually executed.
- [ ] Automated tests asserting response headers and persisted log values.
