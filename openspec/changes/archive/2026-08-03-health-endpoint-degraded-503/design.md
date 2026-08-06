## Context

Today the endpoint computes `overall_status = "healthy" if all(services.values()) else "degraded"` and always returns `JSONResponse` with default status 200. K8s liveness/readiness probes that only check the status code receive a misleading `200 OK` even when the system is degraded.

`get_llm_circuit_breaker()` already exists in `app/services/circuit_breaker.py:272` and exposes `state` and `is_closed`. The Redis cache exposes a connection but no public `ping()`; this change adds a thin `ping()` method.

## Goals / Non-Goals

**Goals:**
- HTTP status reflects operational state (200 healthy, 503 degraded).
- Per-dependency breakdown so operators see which one is down.
- Circuit-breaker state visible per breaker.
- Backward compatible — existing fields stay.

**Non-Goals:**
- Adding a separate `/api/ready` endpoint.
- Reporting individual service latencies.
- Historical health (last 5 minutes uptime, etc.).

## Decisions

### D1: 503 only when degraded; 200 otherwise
No 500. 500 implies the health endpoint itself failed; 503 is the correct semantic for "service alive but dependency degraded".

### D2: `dependencies` keyed by canonical name
- `mongo` (was implicit, now explicit)
- `redis` (new, was implicit-via-cache)
- `vector_store` (already in `services`)
- `llm` (already in `services`)

The legacy `services` map keeps `vector_store` and `llm` for one release cycle, then can be removed.

### D3: `circuit_breakers` keyed by breaker name
Currently only the LLM circuit breaker. The map shape generalizes to additional breakers if added later.

### D4: Three-value enum, not boolean
`healthy` / `degraded` / `down` — degraded means reachable but partial (e.g. high latency, retry exhaustion), down means not reachable. A boolean cannot express that.

## Risks / Trade-offs

- **Risk: 503 surprises Core API** — Mitigation: announce the change in the proposal; existing logic in Core API that branches on body fields keeps working. Only HTTP-level checks change behavior.
- **Risk: redis ping adds latency to health endpoint** — Mitigation: cache the result for ~5s.

## Open Questions

- None.
