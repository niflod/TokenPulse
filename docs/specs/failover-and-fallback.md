# Spec: Automatic Fallback and Failover Gateway

## Problem Statement

Applications relying on external LLM APIs face downtime and broken user experiences when their primary provider (e.g., OpenAI) suffers from HTTP 5xx outages, rate limits (HTTP 429), connection timeouts, or monthly budget exhaustions. Today, developers must write complex custom failover logic in their client code or manually switch base URLs and API keys, creating fragility and latency in incident resolution.

## Solution

TokenPulse Gateway will provide an automatic, zero-code failover mechanism for client applications. When a request to a primary provider fails due to upstream 429 errors, 5xx server errors, connection timeouts, or pre-configured monthly budget limits, the Gateway will automatically and transparently reroute the request to an equivalent fallback model on a secondary provider (e.g., Groq, Mistral, or Ollama) following an administrator-defined priority rule matrix. The client receives the response with explicit telemetry headers indicating that a fallback occurred, and the incident is visibly tagged in the dashboard logs.

## User Stories

1. As a backend developer, I want my API requests to automatically fail over to an alternative provider when the primary provider returns HTTP 429 (Rate Limit / Quota Exceeded), so that my application remains available without manual intervention.
2. As a backend developer, I want requests to fail over to a secondary provider when the primary provider returns HTTP 500, 502, 503, 504 or times out, so that infrastructure incidents at one provider do not impact my service.
3. As a financial administrator, I want requests to automatically reroute to cheaper or local providers when a provider's monthly budget is exhausted, so that my services stay online within budget constraints instead of hard-failing.
4. As an API consumer, I want to inspect HTTP response headers (`X-TokenPulse-Fallback: true`, `X-TokenPulse-Original-Model: ...`) to know if a response came from a fallback provider rather than the requested one.
5. As a dashboard administrator, I want to configure fallback rules in the web UI specifying source models, target models, and priority ranks, so that I have granular control over model equivalence.
6. As a dashboard administrator, I want a default sensible model equivalence matrix provided out-of-the-box (e.g., `gpt-4o` → Groq `llama-3.3-70b-versatile` → Mistral `mistral-large-latest`), so that failover works without requiring initial manual configuration.
7. As a dashboard operator, I want to see a visual `[Fallback]` badge and provider trace on request logs in the dashboard, so that I can audit how often and why failover occurred.
8. As a client application, I want streaming responses (SSE) to support failover if the connection or handshake fails before tokens start streaming, so that user-facing chatbots recover gracefully.
9. As a developer using virtual client keys (`tp_live_...`), I want fallback requests to resolve upstream credentials automatically from TokenPulse without requiring secondary API keys from the client.
10. As a system administrator, I want to enable or disable individual fallback rules via a toggle switch in the UI, so that I can quickly stop failovers to a particular provider during maintenance.

## Implementation Decisions

1. **Fallback Rule Model and Storage**:
   - Create a `FallbackRule` persistence entity storing `source_provider`, `source_model`, `target_provider`, `target_model`, `priority` (lower numbers tried first), and an `enabled` boolean flag.
   - Support wildcards (e.g. `source_model: *`) as fallbacks for unmapped models.
   - Seed default fallback rules upon database initialization if none exist.

2. **Gateway Execution Seam and Flow**:
   - Wrap the upstream request call in an asynchronous retry/failover loop inside the Gateway route handler.
   - If the primary attempt raises a connection/read timeout or returns a qualifying HTTP status (429, 500, 502, 503, 504), inspect available fallback rules ordered by priority.
   - For budget cap violations, skip the primary attempt immediately and route directly to the first eligible fallback candidate.
   - Rewrite the request body JSON to swap the `model` field to the target model, adjust the upstream base URL and authorization headers, and dispatch to the secondary provider.
   - If the first fallback candidate also fails, continue down the priority chain until all eligible targets are exhausted before returning the final error to the client.

3. **Telemetry and Response Headers**:
   - When a fallback succeeds, inject informative HTTP headers into the client response:
     - `X-TokenPulse-Fallback: true`
     - `X-TokenPulse-Original-Provider: <provider>`
     - `X-TokenPulse-Original-Model: <model>`
     - `X-TokenPulse-Actual-Provider: <target_provider>`
     - `X-TokenPulse-Actual-Model: <target_model>`
     - `X-TokenPulse-Fallback-Reason: <status_code|timeout|budget_cap>`
   - Extend `RequestLog` schema with `fallback_triggered: bool`, `original_provider: str`, `original_model: str`, and `fallback_reason: str`.
   - Calculate cost and token metrics using the actual fallback model's pricing table entry.

4. **Configuration API and Dashboard Management**:
   - Provide REST CRUD endpoints (`/api/fallback-rules`) with admin authentication.
   - Add a "Regras de Fallback & Alta Disponibilidade" section in the Dashboard Settings view with creation, deletion, and toggle controls.
   - Render a distinctive status badge on the Request Log table highlighting failover events.

## Testing Decisions

1. **Gateway Failover Behavior**:
   - Verify that simulated 429, 500, 502, 503, 504 responses and timeouts from OpenAI trigger immediate rerouting to the Groq fallback model.
   - Verify that streaming requests that fail during initial connection successfully retry against the fallback target.
   - Verify that requests exceeding the monthly budget skip the primary provider and execute against the fallback target.
   - Verify that `RequestLog` correctly persists both original and actual providers/models and tags `fallback_triggered = True`.
   - Verify that client responses contain the expected `X-TokenPulse-Fallback` headers.

2. **Rule CRUD and Priorities**:
   - Unit and integration tests for `/api/fallback-rules` creating, ordering, toggling, and deleting rules.

## Out of Scope

- Semantic output quality evaluation or automated prompt re-formatting between incompatible chat templates (models are assumed OpenAI-compatible in API format).
- Live mid-stream token failure recovery once token generation has already started.
- Multi-region geo-DNS load balancing (all logic executes within the TokenPulse Gateway node).

## Further Notes

- All supported fallback target providers (Groq, Mistral, Ollama) share OpenAI-compatible chat completion JSON payloads, ensuring clean body translation with minimal runtime overhead.
