# Design

## Categorization Strategy

Each broad except block falls into one of three categories. Apply consistent treatment:

### Category A: Fail-safe (catch, log, continue/return safe default)
- **Examples**: Redis read fails → return `None`; OCR per-image fails → skip that image
- **Treatment**: Replace `except Exception as e` + `logger.error(..., error=str(e))` with `except Exception:` + `logger.exception(...)`
- **Rationale**: `logger.exception` automatically includes traceback. The traceback is the valuable artifact for debugging.

### Category B: Re-raise after logging
- **Examples**: Bookkeeping log before propagating
- **Treatment**: Same as A, but with `raise` instead of return
- **Rationale**: identical reasoning

### Category C: Narrow to specific exception classes
- **When applicable**: When the call's exception contract is known and stable
- **Example for Redis**:
  ```python
  except (ConnectionError, TimeoutError, redis.RedisError) as exc:
      logger.exception("redis_get_failed")
      return None
  ```
- **Trade-off**: catching too narrow may miss legitimate failures; catching too broad masks bugs. Default to Category A unless the call has a documented exception contract.

## Per-File Strategy

### `app/core/redis_cache.py` (11 blocks)
- All fail-safe (cache miss → return None or empty)
- Apply Category A (broad → `logger.exception`)
- Optionally narrow to `redis.RedisError` (Category C) if upstream is consistent

### `app/services/document_processor.py` (2 blocks)
- Both fail-safe in batch processing
- Apply Category A

### `app/services/document_processing/image_extraction.py` (3 blocks)
- Per-image OCR/caption failures shouldn't kill whole document
- Apply Category A (preserve graceful degradation)

### `app/utils/logger.py` (2 blocks)
- MongoDB logging fail-safe (logging itself shouldn't break app)
- Apply Category A

### `app/core/cache_analyzer.py`, `app/core/circuit_breaker.py`, `app/api/batch_routes.py` (3 blocks)
- Apply Category A

## Migration Approach

Use script (similar to standardize-route-exception-handling) to batch-replace patterns. Manual review of each replacement to verify graceful degradation logic is preserved.
