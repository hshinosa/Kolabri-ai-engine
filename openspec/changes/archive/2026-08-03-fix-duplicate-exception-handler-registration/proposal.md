# Fix Duplicate Exception Handler Registration

## Problem Statement

`main.py` registers FastAPI exception handlers **twice** for the same exception classes:

1. Lines 146-147 (added in `standardize-route-exception-handling`):
   ```python
   app.add_exception_handler(StarletteHTTPException, http_exception_handler)
   app.add_exception_handler(RequestValidationError, validation_exception_handler)
   ```

2. Lines 194-258 (legacy from previous session):
   ```python
   @app.exception_handler(Exception)
   async def global_exception_handler(...): ...

   @app.exception_handler(StarletteHTTPException)
   async def http_exception_handler(...): ...

   @app.exception_handler(RequestValidationError)
   async def validation_exception_handler(...): ...
   ```

**Impact**: In FastAPI, **later registration wins** for the same exception key. The legacy decorated handlers at L194-258 override the new handlers from `app/core/error_handlers.py`. Production runs the OLD code path, not the new one.

**How it escaped detection**: The integration test fixture (`integration_app` in `test_api_routes_expanded.py`) was updated to register the NEW handlers manually — so tests pass against new behavior. Production app uses the OLD legacy handlers.

## Proposed Solution

Remove the legacy decorated handlers (`main.py:194-258`) since their logic is now centralized in `app/core/error_handlers.py`. Keep only the explicit `add_exception_handler(...)` calls + the `LLMDegradedError` handler (which is domain-specific and not in the new module).

## Scope

- `main.py` — remove ~60 lines of duplicated handler logic (L194-258 except the `LLMDegradedError` one)
- Verify `LLMDegradedError` handler stays
- Verify `RateLimitExceeded` handler stays (different exception class)
- Smoke test endpoint to verify new handler runs

## Out of Scope

- Refactoring `LLMDegradedError` handler into `error_handlers.py`
- Changing handler behavior (logic stays the same)
