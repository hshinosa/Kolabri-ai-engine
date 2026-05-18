## 1. Error type & config

- [x] 1.1 Tambah `LLMDegradedError(Exception)` di `app/services/llm.py:25-30` dengan `__init__(self, reason: str, retry_after: int)`.
- [x] 1.2 Tambah `LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS: int = 30` ke `app/core/config.py:168`.

## 2. Service wiring

- [x] 2.1 Wrap LLM call dengan `breaker.call(...)` di `OpenAILLMService.generate(...)`. Catch `CircuitBreakerOpenError` → raise `LLMDegradedError(reason="llm_circuit_open", retry_after=max(1, breaker.recovery_timeout))`.
- [x] 2.2 Catch `(RateLimitError, APIConnectionError, APIError)` (post-tenacity-retry, reraise=True) → raise `LLMDegradedError(reason="llm_retry_exhausted", retry_after=settings.LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS)`.

## 3. Exception handler

- [x] 3.1 Tambah `@app.exception_handler(LLMDegradedError)` di `main.py:226-249` yang return 503 + body `{detail:"DEGRADED", outcome:"degraded", reason, message, retry_after, request_id}` + headers `X-Request-ID` dan `Retry-After`.

## 4. Tests

- [x] 4.1 Buat `tests/test_unit/test_llm_degraded.py` — 3 test: breaker open → `LLMDegradedError(reason="llm_circuit_open")`, retry exhaustion → `LLMDegradedError(reason="llm_retry_exhausted", retry_after=settings.LLM_RETRY_DEFAULT_RETRY_AFTER_SECONDS)`, FastAPI handler integration → 503 + outcome="degraded" + Retry-After header.

## 5. Verifikasi

- [x] 5.1 `pytest tests/test_unit/test_llm_degraded.py` → 3 passed.
- [x] 5.2 `python3 -m py_compile app/services/llm.py main.py` exit 0.
- [x] 5.3 `openspec validate map-circuit-breaker-to-degraded-outcome --strict` → valid.
