# Design

## Pattern A: Re-raise after logging (3 occurrences)

### Before
```python
except Exception as e:
    logger.error("csv_export_failed", group_id=group_id, error=str(e))
    raise
```

### After
```python
except Exception:
    logger.exception("csv_export_failed", group_id=group_id)
    raise
```

`logger.exception` automatically includes traceback. Removes redundant `as e` and `str(e)`.

## Pattern B: Structured error response (~15 occurrences)

Pattern B is the trickiest because it's legitimate graceful degradation. The route catches an exception and returns a structured response (e.g., `{"success": False, "error": "..."}`) instead of letting the global handler return a generic 500.

### Before
```python
except Exception as e:
    logger.error("ask_question_failed", error=str(e))
    return AskResponse(
        answer="Maaf, terjadi kesalahan saat memproses pertanyaan...",
        success=False,
        error=str(e),
    )
```

### After
```python
except Exception:
    logger.exception("ask_question_failed", query=request.query[:100])
    return AskResponse(
        answer="Maaf, terjadi kesalahan saat memproses pertanyaan...",
        success=False,
        error="Internal error",
    )
```

Reasoning:
- Logging keeps full traceback via `logger.exception`
- Response body uses generic message — no leak to client
- User-facing answer (Indonesian) tetap helpful

## Pattern C: Health check per-service catches (5 occurrences)

Pattern C in health.py is intentional. Each service ping is wrapped:

```python
try:
    await vector_store._ensure_collection("health_check")
    dependencies["vector_store"] = "healthy"
except Exception as e:
    dependencies["vector_store"] = "unhealthy"
    logger.error("health_check_vector_store_failed", error=str(e))
```

Decision: keep `as e` here because the error string is included in structured log only (not response body). The response body marks service as "unhealthy" without leaking the exception message. This is correct.

Optional improvement: replace with `logger.exception(...)` to get traceback automatically. Apply consistently.

## Migration Strategy

Use a script (similar to standardize-route-exception-handling) untuk batch-replace patterns A and B. Pattern C handled manually (only health.py).

Test impact: tests that assert `error=str(e)` in response body need to be updated to assert generic message OR check that `success=False` is set.
