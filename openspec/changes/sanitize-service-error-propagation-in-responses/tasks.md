## 1. Pre-flight

- [ ] 1.1 Run baseline: `pytest tests/ -q` — 2027 passing
- [ ] 1.2 Audit: `grep -rn "error=str(e)\|'error': str(e)" app/services/`
- [ ] 1.3 List all result objects with `error: Optional[str]` field

## 2. app/services/rag.py

- [ ] 2.1 Identify all `error=str(e)` in `RAGResult` construction
- [ ] 2.2 Replace with `error="Internal error"` (or specific safe message)
- [ ] 2.3 Replace `logger.error(error=str(e))` with `logger.exception(...)` for context
- [ ] 2.4 Add docstring to `RAGResult` documenting safe-by-construction contract

## 3. app/services/orchestration.py

- [ ] 3.1 Same treatment for `DashboardResult` or equivalent

## 4. app/services/goal_validator.py

- [ ] 4.1 Same treatment for `ValidationResult`

## 5. Other service modules (audit)

- [ ] 5.1 Run `grep -rn 'error=str(e)' app/services/`
- [ ] 5.2 For each match: classify and apply pattern

## 6. Update affected tests

- [ ] 6.1 Audit: `grep -rn 'result.error\|.error ==' tests/ | head -20`
- [ ] 6.2 Update tests asserting specific exception strings → assert generic message or `success=False`

## 7. Verify

- [ ] 7.1 `pytest tests/ -q` — passing
- [ ] 7.2 `grep -rn 'error=str(e)' app/services/` — 0 matches
- [ ] 7.3 Manual: trigger error in service, verify result.error is generic
- [ ] 7.4 `openspec validate sanitize-service-error-propagation-in-responses --strict`
