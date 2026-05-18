## 1. Helper

- [x] 1.1 Buat `app/api/guarded_response.py` dengan `RULE_MESSAGE_MAP` (5 rule mapping akademik/off-topic/prompt_injection/toxicity/PII), `DEFAULT_GUARDED_MESSAGE`, dan `guarded_response(rule_id, surface, request_id) -> JSONResponse` yang return body `{detail:"GUARDED", outcome:"guarded", reason, message, request_id}` dengan status 200 untuk chat / 403 untuk non_chat + `X-Request-ID` header.

## 2. Exception handlers

- [x] 2.1 Update `global_exception_handler` di `main.py:174-194` agar body include `outcome:"terminal"`.
- [x] 2.2 Update `http_exception_handler` di `main.py:196-218` agar body include `outcome:"terminal"` hanya untuk status >= 500.

## 3. Call sites

- [x] 3.1 Audit Guardrails call sites di `app/services/rag.py:204` (`check_input` BLOCK → returns RAGResult with polite text) dan `:359` (`check_output`). Saat ini route layer pakai RAGResult yang shape-nya {answer, sources, ...}, tidak pakai HTTPException langsung. Helper `guarded_response()` siap dipakai di S3 (split-routes) untuk surface route-level error path tanpa expand scope di slice ini.
- [x] 3.2 Helper `guarded_response()` tersedia di `app/api/guarded_response.py` siap dipakai. Migrasi call site Guardrails RAGResult → `guarded_response()` adalah follow-up scope karena perlu re-shape `RAGResult` API contract.

## 4. Tests

- [x] 4.1 Buat `tests/test_unit/test_guarded_response.py` dengan 5 test: chat surface 200 + outcome="guarded", non-chat 403 + outcome="guarded", unknown rule fallback ke `DEFAULT_GUARDED_MESSAGE`, request_id header echo, global_exception_handler integration → 500 + outcome="terminal".

## 5. Verifikasi

- [x] 5.1 `pytest tests/test_unit/test_guarded_response.py -v` → 5 passed.
- [x] 5.2 `openspec validate add-guarded-outcome-field --strict` → valid.
