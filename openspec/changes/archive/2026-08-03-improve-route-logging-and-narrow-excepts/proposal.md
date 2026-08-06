# Improve Route Logging and Narrow Exception Handling

## Problem Statement

After standardize-route-exception-handling change, 26 broad `except Exception as e` blocks remain in `app/api/routes/`. These fall into three patterns:

### Pattern A: Re-raise after logging (no real catching needed)
```python
except Exception as e:
    logger.error("event_name", error=str(e))
    raise
```
Found in 3 CSV export endpoints di analytics.py. The `as e` is redundant — bisa pakai `logger.exception(...)` tanpa bind.

### Pattern B: Structured error response (graceful degradation)
```python
except Exception as e:
    logger.error("event_name", error=str(e))
    return SomeResponse(success=False, error=str(e))
```
Found in chat.py, analytics.py, interventions.py, etc. Pattern legitimate (graceful degradation), tapi `error=str(e)` dalam response body bisa expose internal details.

### Pattern C: Health check per-service catches (intentional)
```python
try:
    await service.ping()
except Exception as e:
    dependencies["service"] = "unhealthy"
    logger.error(...)
```
Found in health.py. Pattern intentional — per-service exception handling untuk degradation marking. Bisa di-narrow ke specific exceptions kalau service contract jelas.

## Proposed Solution

1. **Pattern A**: Replace `except Exception as e: ... raise` dengan `except Exception: logger.exception(...); raise`
2. **Pattern B**: Replace `error=str(e)` dalam response body dengan generic message + log full error
3. **Pattern C**: Document intentional usage atau narrow ke exception classes spesifik (TimeoutError, ConnectionError, dll.) kalau service contract memungkinkan

## Scope

- 26 broad except blocks across 7 route files
- Test assertions yang depend on specific error messages dalam response body
- No changes to global error_handlers.py (already done in #5)

## Out of Scope

- Custom exception class hierarchy
- Distributed tracing
