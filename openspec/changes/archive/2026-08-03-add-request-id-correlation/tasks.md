## 1. Spec & Design

- [x] 1.1 Buat `proposal.md`, `design.md`, `tasks.md`, dan delta spec di `specs/ai-engine-observability/spec.md` yang lulus `openspec validate --strict`.

## 2. Middleware

- [x] 2.1 Buat `app/middleware/request_id.py` berisi `RequestIDMiddleware(BaseHTTPMiddleware)` yang membaca/men-validate `X-Request-ID`, generate `uuid4()` saat absent/invalid, set `request.state.request_id`, bind/unbind `structlog.contextvars`, dan echo header di response.

## 3. Wiring di main.py

- [x] 3.1 Import + register `RequestIDMiddleware` setelah `LimitRequestSizeMiddleware` (Starlette LIFO → middleware yang di-add terakhir jadi outermost dan jalan duluan untuk inbound). Catatan: spec asli sempat menulis "SEBELUM"; behavior yang benar adalah middleware menjadi outermost — tercapai dengan menambahkannya **setelah** `LimitRequestSizeMiddleware`.
- [x] 3.2 Update `global_exception_handler`, `http_exception_handler`, dan `validation_exception_handler` agar membaca `request.state.request_id` (fallback ke `uuid4()` lewat helper `_request_id_for`) dan menyertakan `request_id` di response body + `X-Request-ID` di header. Field `detail` dan `message` tetap.

## 4. Mongo logger

- [x] 4.1 Update `MongoLogger.log_activity()` di `app/services/mongodb_logger.py` agar membaca `structlog.contextvars.get_contextvars().get("request_id")` dan menulis `entry["request_id"]` jika ada (tanpa override jika caller sudah set explicit).

## 5. Tests

- [x] 5.1 Buat `tests/test_unit/test_request_id_middleware.py` — 5 test: response carries `X-Request-ID` UUID saat inbound absent; valid UUID di-reuse; invalid value direplace; contextvar unbinds setelah request; HTTP exception response carries id via header.

## 6. Verifikasi

- [x] 6.1 Update `scripts/verify_track_activity_and_health.py` dengan section "add-request-id-correlation" — assert `track-activity` echoes inbound UUID, `/api/health` mengeluarkan `X-Request-ID` valid UUID.
- [x] 6.2 `pytest tests/test_unit/test_request_id_middleware.py` → 5/5 passing. Smoke `tests/test_integration/test_api_routes.py` → 36/36 passing (no regression).
- [x] 6.3 `python3 scripts/verify_track_activity_and_health.py` → 11/11 assertion passing (8 lama + 3 baru request-id). Log lines selama request menunjukkan `request_id=<uuid>` ter-bound otomatis (contoh: `last_message_updated request_id=12345678-1234-5678-1234-567812345678`).
- [x] 6.4 LSP basedpyright tidak terinstall di env ini → fallback `python3 -m py_compile` clean (exit 0) untuk `request_id.py`, `mongodb_logger.py`, `main.py`, `verify_*.py`, dan test baru.
- [x] 6.5 `openspec validate add-request-id-correlation --strict` → "Change 'add-request-id-correlation' is valid".
