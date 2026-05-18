# Sanitize Service Error Propagation to API Responses

## Problem Statement

After cleaning up direct `str(e)` leaks in routes (`improve-route-logging-and-narrow-excepts`), an indirect leak vector remains:

Service layer captures exceptions and stores them in result objects:

```python
# app/services/rag.py:422-438
except Exception as e:
    return RAGResult(
        answer="...",
        success=False,
        error=str(e),  # ← still str(e)
    )

# app/services/orchestration.py:137-139
except Exception as e:
    return DashboardResult(error=str(e), ...)

# app/services/goal_validator.py:447-452
except Exception as e:
    return ValidationResult(error=str(e), ...)
```

Routes that return these results to client (`chat.py:77`, `orchestration.py:46`, `interventions.py:58, 100, 134`) then propagate the leaked error string indirectly.

## Proposed Solution

1. Service layer: capture full error via `logger.exception` AND store generic message in result `.error` field
2. Result objects keep `success=False` for caller logic, but `error` field carries safe message only

### Pattern (Service layer)

```python
# Before
except Exception as e:
    logger.error("rag_query_failed", error=str(e))
    return RAGResult(
        answer="Maaf...",
        success=False,
        error=str(e),
    )

# After
except Exception:
    logger.exception("rag_query_failed", course_id=course_id)
    return RAGResult(
        answer="Maaf...",
        success=False,
        error="Internal error",
    )
```

### Routes don't change

Routes already return `result.error` to client. Now `result.error` is safe by construction.

## Scope

- `app/services/rag.py` (~3 patterns at L422-438)
- `app/services/orchestration.py` (L137-139)
- `app/services/goal_validator.py` (L447-452)
- Other service modules with `result.error = str(e)` pattern (audit)
- Affected tests asserting specific error strings in results

## Out of Scope

- Custom exception class hierarchy
- Refactoring result models
- Changing route behavior (routes already correct after previous change)
