## 1. Pre-flight

- [x] 1.1 Run baseline: `pytest tests/ -q` — 2027 passing
- [x] 1.2 Audit: `grep -rn "error=str(e)\|'error': str(e)" app/services/`
- [x] 1.3 List all result objects with `error: Optional[str]` field

## 2. app/services/rag.py

- [x] 2.1 Identify all `error=str(e)` in `RAGResult` construction
- [x] 2.2 Replace with `error="Internal error"` (or specific safe message)
- [x] 2.3 Replace `logger.error(error=str(e))` with `logger.exception(...)` for context
- [x] 2.4 Add docstring to `RAGResult` documenting safe-by-construction contract

## 3. app/services/orchestration.py

- [x] 3.1 Same treatment for `DashboardResult` or equivalent

## 4. app/services/goal_validator.py

- [x] 4.1 Same treatment for `ValidationResult`

## 5. Other service modules (audit)

- [x] 5.1 Run `grep -rn 'error=str(e)' app/services/`
- [x] 5.2 For each match: classify and apply pattern

## 6. Update affected tests

- [x] 6.1 Audit: `grep -rn 'result.error\|.error ==' tests/ | head -20`
- [x] 6.2 Update tests asserting specific exception strings → assert generic message or `success=False`

## 7. Verify

- [x] 7.1 `pytest tests/ -q` — passing
- [x] 7.2 `grep -rn 'error=str(e)' app/services/` — 0 matches
- [x] 7.3 Manual: trigger error in service, verify result.error is generic
- [x] 7.4 `openspec validate sanitize-service-error-propagation-in-responses --strict`
