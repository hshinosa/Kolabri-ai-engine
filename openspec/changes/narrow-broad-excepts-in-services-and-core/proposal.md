# Narrow Broad Exception Handlers in Services and Core

## Problem Statement

After previous refactor, broad `except Exception` blocks remain across `app/services/` and `app/core/`:

| Location | Count | Pattern |
|---|---|---|
| `app/core/redis_cache.py` | 11 | `except Exception as e: logger.error(..., error=str(e))` |
| `app/services/document_processor.py` | 2 | broad catches in batch processing |
| `app/services/document_processing/image_extraction.py` | 3 | OCR/vision per-image catches |
| `app/api/batch_routes.py` | 1 | batch background task |
| `app/core/circuit_breaker.py` | 1 | health check |
| `app/utils/logger.py` | 2 | mongo logging fail-safe |
| `app/core/cache_analyzer.py` | 1 | cache analysis |

Total: ~21 broad excepts in `app/` outside routes.

Many are legitimate (graceful degradation, fail-safe logging), but they all use `error=str(e)` which:
- Misses traceback info
- Could leak details if the error string is later propagated to response

## Proposed Solution

For each broad except block, classify and apply:

### Category A: Fail-safe (catch, log, continue)
```python
# Before
except Exception as e:
    logger.error("event", error=str(e))
    return None

# After
except Exception:
    logger.exception("event")
    return None
```

### Category B: Catch and re-raise (just for logging)
```python
# Before
except Exception as e:
    logger.error("event", error=str(e))
    raise

# After
except Exception:
    logger.exception("event")
    raise
```

### Category C: Narrow to specific exceptions (where contract allows)
```python
# Before (Redis)
except Exception as e:
    logger.error("redis_get_failed", error=str(e))
    return None

# After (Redis)
except (ConnectionError, TimeoutError, redis.RedisError) as exc:
    logger.exception("redis_get_failed")
    return None
```

## Scope

- `app/core/redis_cache.py` — 11 blocks, mostly Category A (fail-safe cache reads/writes)
- `app/services/document_processor.py` — 2 blocks, Category A
- `app/services/document_processing/image_extraction.py` — 3 blocks, Category A (per-image OCR)
- `app/api/batch_routes.py` — 1 block, Category A
- `app/core/circuit_breaker.py` — 1 block
- `app/utils/logger.py` — 2 blocks
- `app/core/cache_analyzer.py` — 1 block

## Out of Scope

- Refactoring exception class hierarchy
- Changing graceful degradation behavior
- Routes (already handled in `improve-route-logging-and-narrow-excepts`)
