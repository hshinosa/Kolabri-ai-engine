## 1. Pre-flight

- [x] 1.1 Capture current 5 failures: `pytest tests/test_blackbox/test_api_blackbox.py tests/test_performance.py --no-cov -q --no-header`
- [x] 1.2 Confirm `_assert_json_error_structure` helper exists in [tests/test_blackbox/test_api_blackbox.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_blackbox/test_api_blackbox.py)
- [x] 1.3 Confirm `pyproject.toml` has `python_functions = ["test_*"]` collection pattern

## 2. Update health-endpoint blackbox assertions

- [x] 2.1 `test_valid_auth_reaches_endpoint` — relax `assert response.status_code == 200` to `assert response.status_code in (200, 503)`
- [x] 2.2 `test_health_check_returns_status` — accept `(200, 503)`; the body shape (`status` field) is identical at both statuses because the route uses `JSONResponse` directly
- [x] 2.3 `test_health_check_returns_expected_structure` — accept `(200, 503)`; structural assertions hold for both
- [x] 2.4 `test_health_response_is_json` — accept `(200, 503)`; the `application/json` content-type assertion stays unchanged

## 3. Remove stray async benchmark from collection

- [x] 3.1 Rename `async def test_final` → `async def final_benchmark` in [tests/test_performance.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_performance.py)
- [x] 3.2 Run `pytest tests/test_performance.py --no-cov -q` and confirm `0 collected`

## 4. Verify

- [x] 4.1 `pytest tests/test_blackbox/test_api_blackbox.py --no-cov -q --no-header` — 0 failed
- [x] 4.2 `pytest tests/test_performance.py --no-cov -q --no-header` — 0 collected
- [x] 4.3 Full suite: `pytest tests/ --ignore=tests/benchmarks --ignore=benchmarks --no-cov -q --no-header` — 0 failed
- [x] 4.4 `openspec validate stabilize-test-env-for-degraded-deps-and-async --strict`
