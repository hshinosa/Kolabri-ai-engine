# Design

## Bucket 1: Health Endpoint Test Assertions

### Current vs Target

The 4 affected tests share a hidden assumption: "if auth passes, the endpoint returns 200". After `health-endpoint-degraded-503`, that's wrong — auth still passes, but the body is now 503 because no backend is reachable in test env.

The 503 body comes from [app/api/routes/health.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/routes/health.py#L98), which emits the same `HealthResponse` payload via `JSONResponse(status_code=503, content=body.model_dump(...))`. Because the route returns `JSONResponse` directly (not `raise HTTPException`), the response body is the **raw HealthResponse dict** at both 200 and 503. `http_exception_handler` is **not** applied.

That means the existing structural assertions (`assert "status" in data`, `assert "services" in data`, etc.) work unchanged at 503 — the only thing wrong is the `status_code == 200` assertion.

### Decision: relax the status assertion only

```python
def test_health_check_returns_status(self, client, auth_headers):
    response = client.get("/api/health", headers=auth_headers)

    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
```

Same shape, broader status set. No need to gate body assertions on a status branch — the body is identical at 200 and 503.

### Why not stub the dependencies?

Three options were considered:

1. **Stub Redis/Qdrant via `monkeypatch` in conftest** — would give true 200 in tests. **Rejected**: requires non-trivial fixtures across 4+ services, makes tests less honest (they no longer exercise the real handler logic), and inflates conftest scope. Blackbox tests should reflect real behavior.
2. **Mark tests `@pytest.mark.requires_qdrant` and skip in laptop env** — **Rejected**: silently skipping degrades signal. The tests *are* runnable; they just need to assert the right contract.
3. **Update assertions to accept the documented 503 path (chosen)** — **Accepted**: zero infra change, exercises the real handler, asserts the actual contract.

### `test_valid_auth_reaches_endpoint` minimal change

This test only validates that a valid bearer token is not rejected by the auth middleware. The endpoint behavior past auth is irrelevant. Update to:
```python
def test_valid_auth_reaches_endpoint(self, client, auth_headers):
    response = client.get("/api/health", headers=auth_headers)
    assert response.status_code in (200, 503)
```

This is the smallest-correct change. Auth pass means the response is **not** 401/403.

## Bucket 2: test_performance.py Rename

### Why rename and not delete?

The file is committed history. Deleting it loses the benchmark. Renaming `test_final` → `final_benchmark` is one line, leaves the file usable as `python tests/test_performance.py` (it has no `if __name__ == "__main__":` guard but the function is callable), and matches the project's existing `python_functions = ["test_*"]` collection pattern in `pyproject.toml`.

### Risk of accidental re-collection

Any future async function named `test_*` in `tests/` outside the conftest-aware blackbox/unit dirs would re-introduce the same failure. Mitigation: out of scope for this change. If it recurs, follow-up scope can add `pytest-asyncio` to `pyproject.toml` once async tests are intentionally adopted.

## Verification

After the change:
- `pytest tests/test_blackbox/test_api_blackbox.py --no-cov -q` → 0 failed (was 4)
- `pytest tests/test_performance.py --no-cov -q` → 0 collected, 0 failed (was 1)
- `pytest tests/ --ignore=tests/benchmarks --ignore=benchmarks --no-cov -q --no-header` → 0 failed (delta: −5 from prior baseline)
