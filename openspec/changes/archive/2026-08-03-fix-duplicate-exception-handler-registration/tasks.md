## 1. Pre-flight

- [x] 1.1 Run baseline: `pytest tests/ -q` — 2027 passing
- [x] 1.2 Read `main.py:194-258` to capture legacy handler behavior
- [x] 1.3 Compare with `app/core/error_handlers.py`

## 2. Remove duplicate handlers

- [x] 2.1 Remove `@app.exception_handler(Exception)` block (`main.py:194-213`)
- [x] 2.2 Remove `@app.exception_handler(StarletteHTTPException)` block (`main.py:215-236`)
- [x] 2.3 Remove `@app.exception_handler(RequestValidationError)` block (`main.py:238-255`)
- [x] 2.4 Keep `@app.exception_handler(LLMDegradedError)` block (`main.py:257-...`)
- [x] 2.5 Remove unused imports if any

## 3. Verify production setup matches test fixture

- [x] 3.1 Audit `main.py` — `app.add_exception_handler` at L146-147 only
- [x] 3.2 Audit `tests/test_integration/test_api_routes_expanded.py` `integration_app` fixture matches
- [x] 3.3 Confirm `ExceptionMiddleware` registered after exception handlers

## 4. Smoke test

- [x] 4.1 Add test in `tests/test_unit/test_main_exception_handlers.py` that:
  - Creates app via main.py setup (or replicates registration order)
  - Triggers `RuntimeError` from a route
  - Verifies response: `status_code=500`, `detail="Internal server error"`, `request_id` field present

## 5. Verify

- [x] 5.1 `pytest tests/ -q` — passing
- [x] 5.2 `openspec validate fix-duplicate-exception-handler-registration --strict`
- [x] 5.3 Manual: `grep "@app.exception_handler" main.py | wc -l` returns ≤ 1 (LLMDegradedError only)
