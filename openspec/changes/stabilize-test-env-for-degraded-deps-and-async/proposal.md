# Stabilize Test Environment For Degraded Dependencies And Async Markers

## Problem Statement

After all the recent OpenSpec changes, the full test suite still surfaces 5 failures, all environmental. They split into two distinct buckets:

### Bucket 1: Black-box health/auth tests assert healthy backends (4 failures)

[tests/test_blackbox/test_api_blackbox.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_blackbox/test_api_blackbox.py) drives the real FastAPI app via `TestClient`. The `/api/health` endpoint correctly walks every dependency (Qdrant, Redis, Mongo, LLM, reranker) and returns 503 when any are unreachable — exactly the contract introduced by the completed `health-endpoint-degraded-503` change. In a developer-laptop test environment, none of those backends are available, so the endpoint returns 503 every time.

The current tests assert `response.status_code == 200`. That assertion contradicts the documented degraded-503 contract:

| Test | Endpoint | Current assertion | Actual response in test env |
|---|---|---|---|
| `TestHealthAndMonitoringEndpoints::test_health_check_returns_status` | `/api/health` | `200` | `503` |
| `TestHealthAndMonitoringEndpoints::test_health_check_returns_expected_structure` | `/api/health` | `200` | `503` |
| `TestResponseStructure::test_health_response_is_json` | `/api/health` | `200` | `503` |
| `TestAuthMiddleware::test_valid_auth_reaches_endpoint` | `/api/health` | `200` | `503` |

The tests are testing the wrong thing: **they want to verify the endpoint reachable past auth**, not that backends are healthy. They should accept `{200, 503}` and validate the response body shape regardless.

### Bucket 2: Stray async test without async runner (1 failure)

[tests/test_performance.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_performance.py) is a one-off manual benchmark script that hits an external server `http://43.228.214.145:8317/v1` and prints comparison statistics. It defines `async def test_final()` — pytest's collector picks it up as a test, but no `pytest-asyncio` runner is installed for top-level tests, so it errors out with:

```
Failed: async def functions are not natively supported.
```

This is not a real test. It's a developer benchmark that was committed as `tests/test_performance.py` by accident. It hardcodes a remote IP, no fixtures, no assertions — just `print` statements.

## Proposed Solution

### Bucket 1 fix: align assertions with the degraded-503 contract

For every test that exercises `/api/health` purely to check **the endpoint is reachable through auth**, change `assert response.status_code == 200` to `assert response.status_code in (200, 503)`. Also extend body-shape assertions to cover the 503 path: a 503 health response goes through `http_exception_handler` so its body is `{"detail": "REQUEST_ERROR", "message": "An error occurred", "outcome": "terminal", "request_id": ...}` — which is fundamentally different from the 200 path's `HealthResponse` (`{"status", "version", "timestamp", "services", ...}`). Tests need to gate the structural assertions on `status_code == 200`.

Specifically:

1. `test_valid_auth_reaches_endpoint` — only checks auth flow. Update to `assert response.status_code in (200, 503)`.
2. `test_health_check_returns_status` — gate the `assert "status" in data` on 200, otherwise validate the sanitized error body.
3. `test_health_check_returns_expected_structure` — same gating.
4. `test_health_response_is_json` — `application/json` content type assertion holds for both 200 and 503; just relax the status assertion.

### Bucket 2 fix: remove the stray manual benchmark from collection

Two reasonable options:

- **Option A**: Delete [tests/test_performance.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_performance.py). It hardcodes a remote IP, has no assertions, and predates the rest of the suite. Move it to `scripts/manual/benchmark_priority_phases.py` if the historical record is desired (out of scope here).
- **Option B**: Rename `test_final` → `final_benchmark` so pytest's collector skips it (only functions matching `test_*` are collected per `pyproject.toml`).

This change picks **Option B** — minimal-impact: rename the function, keep the file. That preserves the developer benchmark for future ad-hoc runs (`python tests/test_performance.py` still works if invoked manually), removes the false test failure, and leaves git history intact.

## Scope

- [tests/test_blackbox/test_api_blackbox.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_blackbox/test_api_blackbox.py) — relax 4 health-endpoint assertions to accept the documented degraded-503 outcome
- [tests/test_performance.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_performance.py) — rename `test_final` → `final_benchmark` so pytest does not collect it

## Out of Scope

- Adding `pytest-asyncio` plugin or making async pytest support project-wide (no current async test uses pytest as the runner — async unit tests already use `asyncio.run(...)` inside sync test functions and that pattern works)
- Standing up real Redis/Qdrant for blackbox tests in CI (orthogonal infra concern)
- Changing the 503 contract or `HealthResponse` schema
- Refactoring `test_performance.py` into a real benchmark suite

## Why Now

These 5 failures masked the otherwise-green suite. Closing them brings the local pytest baseline to 0 failures and gives every future change a clean signal to detect regressions. Both fixes are test-only, low-risk, and document existing production contracts (degraded-503, no-async-collection) instead of changing them.
