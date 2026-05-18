# Design

## Root Cause

When `standardize-route-exception-handling` was implemented, the new handlers were added at `main.py:146-147` BEFORE the existing legacy handlers at `main.py:194-258` were noticed. FastAPI's `add_exception_handler` registers handlers in a dict keyed by exception class — later registration overwrites earlier.

## Verification (current state)

```python
# main.py L146-147 (NEW, added in standardize-route-exception-handling)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# main.py L194-258 (LEGACY, from previous session)
@app.exception_handler(Exception)
async def global_exception_handler(...): ...

@app.exception_handler(StarletteHTTPException)  # OVERWRITES line 146
async def http_exception_handler(...): ...

@app.exception_handler(RequestValidationError)  # OVERWRITES line 147
async def validation_exception_handler(...): ...

@app.exception_handler(LLMDegradedError)  # KEEP — unique
async def llm_degraded_exception_handler(...): ...
```

## Migration Strategy

1. Read `main.py:194-258` to understand legacy handler logic
2. Compare with `app/core/error_handlers.py` to confirm new handlers cover same cases
3. Remove legacy handlers EXCEPT `LLMDegradedError` (domain-specific, not duplicated)
4. Keep `ExceptionMiddleware` (catches unhandled `Exception` — matches what `global_exception_handler` did)
5. Add smoke test that triggers an unhandled exception and verifies response shape matches new format (`{"detail": "Internal server error", "request_id": ...}`)

## Backward Compat

Response shape might differ between old and new handlers:
- OLD: probably `{"detail": "..."}` (no request_id)
- NEW: `{"detail": "...", "request_id": "..."}` — additive, safe

Frontend / core-api consumers might key on specific `detail` strings — verify with grep before merging.
