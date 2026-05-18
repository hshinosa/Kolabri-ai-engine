# Design

## Audit Strategy

Identify all service-layer code that:

1. Catches an exception
2. Returns a result object (Pydantic model, dataclass, or dict)
3. Sets an `error` or similar field to `str(e)`

Use grep to find candidates:

```bash
grep -rn "error=str(e)\|error=str(exc)\|'error': str(e)\|\"error\": str(e)" app/services/
```

Also audit:

```bash
grep -rn "RAGResult\|DashboardResult\|ValidationResult" app/services/ | grep -v "test_"
```

## Treatment Per File

### `app/services/rag.py`

`RAGResult` dataclass has `error: Optional[str]` field. Multiple call sites set it to `str(e)`.

Treatment:
- Replace `error=str(e)` with `error="Internal error"` in result construction
- Use `logger.exception(...)` for full detail capture
- Keep `success=False` and other context fields

### `app/services/orchestration.py`

`DashboardResult` similar pattern.

### `app/services/goal_validator.py`

`ValidationResult` similar pattern.

## Consumer Trust Boundary

Once service layer guarantees `result.error` is safe, routes can return it as-is to client without additional sanitization. Document this contract in `app/services/rag.py` (and others) docstrings:

```python
@dataclass
class RAGResult:
    """RAG pipeline result.

    Note: `error` field contains user-safe messages only.
    Internal exception details are logged via logger.exception, not exposed.
    """
    answer: str
    success: bool
    error: Optional[str] = None
```

## Test Impact

Tests that assert `result.error == "<specific exception msg>"` need to be updated to assert `result.error == "Internal error"` or check for `result.success is False` instead.

## Defense in Depth

Even after this change, consider adding a `Pydantic.validator` on response models that ensures `error` field doesn't contain stack-trace-like patterns (e.g., file paths, "Traceback", `KeyError`, etc.). Optional layer for paranoid clients.
