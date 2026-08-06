# Service and Core Layer Exception Handling

## ADDED Requirements

### Requirement: Service layer SHALL use logger.exception for caught exceptions

Service modules in `app/services/` and infrastructure modules in `app/core/`, `app/utils/`, `app/api/batch_routes.py` SHALL NOT use `logger.error(..., error=str(e))` pattern when catching exceptions. They MUST use `logger.exception(...)` to automatically capture traceback.

#### Scenario: Cache read failure

- Given `app/core/redis_cache.py` catches an exception during cache read
- When the handler logs the error
- Then it MUST use `logger.exception("cache_get_failed", key=cache_key)`
- And it MUST NOT use `logger.error("cache_get_failed", error=str(e))`
- And the function MUST still return a safe default (None or empty)

#### Scenario: Per-image OCR failure during batch document processing

- Given `app/services/document_processing/image_extraction.py` processes multiple images
- When OCR fails for one image
- Then the handler MUST log via `logger.exception(...)`
- And processing MUST continue for remaining images
- And the failed image MUST NOT cause the entire document to fail
