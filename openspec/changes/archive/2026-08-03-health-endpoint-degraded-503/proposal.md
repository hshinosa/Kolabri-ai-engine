## Why

The current `/api/health` endpoint (`app/api/routes.py:599-642`) returns HTTP 200 with `status="degraded"` even when dependencies fail. This is silent for HTTP-level health probes (Kubernetes, load balancers) which only inspect the status code. The endpoint also reports only `vector_store` and `llm` despite the codebase having a Redis cache (`app/core/redis_cache.py`), Mongo (`app/services/mongodb_logger.py`), and a circuit breaker (`app/services/circuit_breaker.py`) that all have meaningful health states. Slice H2 in `harden-ai-engine-safety-and-observability` § H calls for this fix.

## What Changes

- Extend `HealthResponse` schema with:
  - `dependencies: dict[str, str]` carrying `mongo`, `redis`, `vector_store`, `llm` with values `"healthy"` / `"degraded"` / `"down"`.
  - `circuit_breakers: dict[str, str]` keyed by breaker name, value is `"closed"` / `"open"` / `"half_open"`.
- When overall status is degraded (any dependency not healthy), the endpoint MUST return HTTP 503 instead of 200.
- The existing `services` map and `reranker_enabled` field remain for backward compatibility.

## Capabilities

### Modified Capabilities

- `ai-engine-observability` — adds the requirement that operationally-degraded health states surface as HTTP 503 with per-dependency breakdown.

## Impact

- `app/api/schemas.py` — extend `HealthResponse`.
- `app/api/routes.py` (or `app/api/routes/health.py` if S3 has shipped first) — extend the handler.
- `app/services/redis_cache.py`, `app/services/mongodb_logger.py` — expose lightweight `ping()` / `is_healthy()` if not already present.
- `tests/test_integration/test_api_routes.py` — extend health-check test to assert degraded → 503.
