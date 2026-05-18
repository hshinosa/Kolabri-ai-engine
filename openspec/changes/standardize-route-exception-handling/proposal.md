# Standardize Route Exception Handling

## Problem Statement

30+ route handlers menggunakan pattern:

```python
try:
    ...
except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))
```

Issue:
- `str(e)` bocor implementation details (stack trace, internal paths, DB errors) ke caller
- Tidak distinguish client error (4xx) vs server error (5xx)
- Tidak ada structured logging dengan request_id
- Inconsistent error response shape

Kontes: ai-engine di belakang core-api gateway, tapi defense-in-depth tetap penting — error log dari core-api juga bisa expose details.

## Proposed Solution

1. Tambah global exception handlers di `main.py`:
   - `HTTPException` → pass-through dengan structured log
   - `ValidationError` (Pydantic) → 422 dengan sanitized detail
   - `Exception` (catchall) → 500 dengan generic message + log full error
2. Tambah `app/core/error_handlers.py` untuk centralize logic
3. Refactor route handlers — hapus broad `except Exception` blocks, biarkan global handler yang handle
4. Untuk error spesifik (404 not found, 400 bad input), explicit raise `HTTPException` di route

## Scope

- `main.py` — register exception handlers
- `app/core/error_handlers.py` (baru) — handler functions
- `app/api/routes/*.py` — refactor 30+ broad except blocks
- Tests yang assert error format — update jika perlu

## Out of Scope

- Custom exception class hierarchy (deferred)
- Distributed tracing
