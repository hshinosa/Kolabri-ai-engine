## 1. Pre-flight

- [ ] 1.1 Run baseline: `pytest tests/ -q` — 2009 passing
- [ ] 1.2 Grep semua `except Exception as e` di routes: `grep -rn "except Exception as e" app/api/routes/`
- [ ] 1.3 List existing exception handlers di `main.py`

## 2. Create error_handlers.py

- [ ] 2.1 Buat `app/core/error_handlers.py`
- [ ] 2.2 Implement `unhandled_exception_handler` — log full + return generic 500
- [ ] 2.3 Implement `http_exception_handler` — pass-through + structured log
- [ ] 2.4 Implement `validation_exception_handler` — 422 dengan field errors
- [ ] 2.5 Add request_id propagation dari `request.state`

## 3. Wire handlers in main.py

- [ ] 3.1 Import handlers
- [ ] 3.2 `app.add_exception_handler(HTTPException, http_exception_handler)`
- [ ] 3.3 `app.add_exception_handler(RequestValidationError, validation_exception_handler)`
- [ ] 3.4 `app.add_exception_handler(Exception, unhandled_exception_handler)`

## 4. Refactor route handlers

- [ ] 4.1 `routes/efficiency.py` (5 except blocks) — hapus broad excepts
- [ ] 4.2 `routes/goals.py` (2 except blocks)
- [ ] 4.3 `routes/health.py` (5 except blocks) — keep specific service-check excepts (intentional degradation)
- [ ] 4.4 `routes/monitoring.py` (4 except blocks)
- [ ] 4.5 `routes/documents.py` (3+ except blocks)
- [ ] 4.6 `routes/analytics.py` — review semua except
- [ ] 4.7 `routes/chat.py`, `groups.py`, `interventions.py`, `orchestration.py` — review

## 5. Update tests

- [ ] 5.1 Tests yang assert `{"detail": "specific error message"}` — update untuk assert generic 500 atau specific HTTPException codes
- [ ] 5.2 Add new tests untuk error_handlers.py

## 6. Verify

- [ ] 6.1 `pytest tests/ -q` — passing
- [ ] 6.2 Manual test: trigger error, verify response shape `{"detail": "...", "request_id": "..."}`
- [ ] 6.3 Manual test: verify logs carry request_id
- [ ] 6.4 `openspec validate standardize-route-exception-handling --strict`
