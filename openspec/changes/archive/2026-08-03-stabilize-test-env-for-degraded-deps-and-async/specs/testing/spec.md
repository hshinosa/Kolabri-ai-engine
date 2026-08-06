# Black-box Health Endpoint Test Contract

## ADDED Requirements

### Requirement: Health endpoint blackbox tests SHALL accept 200 or 503

Tests in `tests/test_blackbox/test_api_blackbox.py` that exercise `/api/health` SHALL accept `response.status_code in (200, 503)`. The 503 response body MUST contain the same `HealthResponse`-shape fields as the 200 response (the route emits the same `JSONResponse` payload at both status codes), so the tests' structural assertions on `status`, `version`, `timestamp`, `services`, and `data["services"]["vector_store"|"llm"]` MUST hold for both 200 and 503.

#### Scenario: All backends unreachable in laptop env

- Given the test environment has no Qdrant, Redis, or Mongo
- When the test calls `GET /api/health` with valid auth
- Then `response.status_code` MUST be 503
- And `response.json()` MUST contain `status`, `version`, `timestamp`, `services`
- And `response.json()["status"]` MUST equal `"degraded"`
- And the test MUST NOT fail

#### Scenario: All backends healthy in CI with stack

- Given the test environment has all backends reachable
- When the test calls `GET /api/health` with valid auth
- Then `response.status_code` MUST be 200
- And `response.json()` MUST contain `status`, `version`, `timestamp`, `services`
- And `response.json()["status"]` MUST equal `"healthy"`

#### Scenario: Auth-only check on /api/health

- Given a test that only verifies `/api/health` is reachable past auth middleware
- When the test calls `GET /api/health` with valid auth
- Then the test MUST assert `response.status_code in (200, 503)` (not 401/403)
- And the test MUST NOT make further assumptions about backend health

### Requirement: Pytest SHALL NOT collect manual benchmark scripts as tests

Files under `tests/` that contain manual benchmark scripts (no fixtures, no assertions, hard-coded external URLs) SHALL NOT define functions matching the `test_*` collection pattern. They MUST use a non-`test_` name (for example `final_benchmark`) so the pytest collector skips them.

#### Scenario: Manual benchmark inside tests/ directory

- Given `tests/test_performance.py` contains an `async` function with no assertions and a hard-coded external URL
- When `pytest tests/` runs
- Then the function MUST NOT be collected as a test
- And running pytest MUST NOT produce an "async def functions are not natively supported" failure
- And the file MAY remain in `tests/` for historical purposes
