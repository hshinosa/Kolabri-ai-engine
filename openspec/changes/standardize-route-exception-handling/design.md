# Design

## Approach

### Global Exception Handler

`main.py`:

```python
from app.core.error_handlers import (
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
```

### Handler Implementations

`app/core/error_handlers.py`:

```python
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )
```

### Route Refactoring Pattern

**Before:**
```python
@router.post("/example")
async def example(payload: ExamplePayload):
    try:
        result = await service.do_thing(payload)
        return {"data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**After:**
```python
@router.post("/example")
async def example(payload: ExamplePayload):
    result = await service.do_thing(payload)
    return {"data": result}
    # Exception handled by global handler — logs with request_id, returns generic 500
```

Untuk error semantik (e.g., resource not found):
```python
if not result:
    raise HTTPException(status_code=404, detail="Resource not found")
```

### Domain Exception → HTTP Mapping

Optional: domain exceptions (sudah ada di codebase: `LLMDegradedError`, `GuardrailViolationError`) di-map ke HTTP status di handler:

| Exception | HTTP Status |
|---|---|
| `LLMDegradedError` | 503 |
| `GuardrailViolationError` | 422 |
| `DocumentNotFoundError` (jika ada) | 404 |
| `Exception` (catchall) | 500 |

## Backward Compat

Response shape: `{"detail": "...", "request_id": "..."}` — backward compatible dengan FastAPI default `{"detail": "..."}`.
