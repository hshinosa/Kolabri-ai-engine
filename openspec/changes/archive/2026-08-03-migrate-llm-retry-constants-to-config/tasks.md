## 1. Discovery

- [x] 1.1 `rtk grep` semua referensi `RETRY_DELAY_BASE`, `RETRY_DELAY_MULTIPLIER`, `TIMEOUT_CONNECT`, `TIMEOUT_READ`, `MAX_RETRIES` di luar `app/services/llm.py` — ditemukan di `tests/test_unit/test_llm.py:19-21,72` (import + assertion). Test diupdate untuk import dari `settings`.

## 2. Config

- [x] 2.1 Tambah section `# LLM Retry & Timeout` di `app/core/config.py:162-167` dengan 5 setting baru: `LLM_MAX_RETRIES=3`, `LLM_RETRY_DELAY_BASE=1.0`, `LLM_RETRY_DELAY_MULTIPLIER=2.0`, `LLM_TIMEOUT_CONNECT_SECONDS=10.0`, `LLM_TIMEOUT_READ_SECONDS=90.0`.

## 3. Service refactor

- [x] 3.1 Update `httpx.Timeout(...)` di `llm.py:60-65` agar `connect=settings.LLM_TIMEOUT_CONNECT_SECONDS, read=settings.LLM_TIMEOUT_READ_SECONDS` dan `AsyncOpenAI(..., max_retries=settings.LLM_MAX_RETRIES)`.
- [x] 3.2 Update `@retry(...)` decorator di `llm.py:113-118` agar `stop=stop_after_attempt(settings.LLM_MAX_RETRIES)` dan tenacity wait pakai `settings.LLM_RETRY_DELAY_*` di branch non-testing.
- [x] 3.3 Hapus 5 module constants `MAX_RETRIES`, `RETRY_DELAY_BASE`, `RETRY_DELAY_MULTIPLIER`, `TIMEOUT_CONNECT`, `TIMEOUT_READ` di `llm.py:19-25`.

## 4. Verifikasi

- [x] 4.1 `pytest tests/test_unit/test_llm.py tests/test_unit/test_circuit_breaker.py -v` → 42 passed.
- [x] 4.2 `python3 -m py_compile app/services/llm.py app/core/config.py` exit 0.
- [x] 4.3 `openspec validate migrate-llm-retry-constants-to-config --strict` → valid.
