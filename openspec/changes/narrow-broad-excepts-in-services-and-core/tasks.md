## 1. Pre-flight

- [x] 1.1 Run baseline: `pytest tests/ -q` — 2027 passing
- [x] 1.2 Audit per-file: `grep -c "except Exception as e" app/services/*.py app/core/*.py app/utils/*.py app/api/batch_routes.py`

## 2. app/core/redis_cache.py (11 blocks)

- [x] 2.1 Replace `except Exception as e` + `logger.error(error=str(e))` with `except Exception` + `logger.exception(...)`
- [x] 2.2 Verify cache miss behavior unchanged (return None / safe default)
- [x] 2.3 Run cache-related tests

## 3. app/services/document_processor.py (2 blocks)

- [x] 3.1 Identify lines (446, 638)
- [x] 3.2 Apply Category A
- [x] 3.3 Run document processor tests

## 4. app/services/document_processing/image_extraction.py (3 blocks)

- [x] 4.1 Identify lines (113, 237, 294)
- [x] 4.2 Apply Category A (per-image fail-safe)
- [x] 4.3 Run image_extraction tests + integration tests

## 5. Other files (5 blocks)

- [x] 5.1 `app/api/batch_routes.py:276`
- [x] 5.2 `app/core/circuit_breaker.py:104`
- [x] 5.3 `app/utils/logger.py:191, 296`
- [x] 5.4 `app/core/cache_analyzer.py:133`

## 6. Verify

- [x] 6.1 `pytest tests/ -q` — passing
- [x] 6.2 `grep -rn "except Exception as e" app/ | grep -v tests/` — minimal (only intentional with comment)
- [x] 6.3 No `error=str(e)` in `logger.error` or `logger.warning` (use logger.exception)
- [x] 6.4 `openspec validate narrow-broad-excepts-in-services-and-core --strict`
