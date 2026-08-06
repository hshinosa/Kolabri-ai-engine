## 1. Helper

- [x] 1.1 Buat `app/core/guardrail_diagnostics.py` dengan `log_guardrail_decision(result, surface, route)`. Skip emit untuk `ALLOW` tanpa triggered_rules. `request_id` ditambahkan otomatis lewat `structlog.contextvars` (sudah wired di `add-request-id-correlation`).

## 2. Call sites

- [x] 2.1 Wire ke `app/services/rag.py:204` setelah `check_input(query)` → `log_guardrail_decision(guardrail_result, surface="input", route="rag.execute_query")`.
- [x] 2.2 Wire ke `app/services/rag.py:359` setelah `check_output(...)` → `log_guardrail_decision(output_check, surface="output", route="rag.execute_query")`.

## 3. Tests

- [x] 3.1 Buat `tests/test_unit/test_guardrail_diagnostics.py` dengan 4 test: BLOCK emits log dengan benar, SANITIZE emits log, ALLOW tanpa triggered_rules skip log, ALLOW dengan triggered_rules tetap emit. Pakai `structlog.testing.capture_logs`.
- [x] 3.2 Test request_id correlation otomatis (sudah dijamin oleh `add-request-id-correlation` slice).

## 4. Verifikasi

- [x] 4.1 `pytest tests/test_unit/test_guardrail_diagnostics.py -v` → 4 passed.
- [x] 4.2 `python3 -m py_compile app/services/rag.py app/core/guardrail_diagnostics.py` exit 0.
- [x] 4.3 `openspec validate structured-guardrail-diagnostics --strict` → valid.
