## 1. Schema

- [x] 1.1 Extend `HealthResponse` di `app/api/schemas.py:15-22` dengan `dependencies: Dict[str, str] = {}` dan `circuit_breakers: Dict[str, str] = {}`. Field `services` dan `reranker_enabled` tetap.

## 2. Dependency probes

- [x] 2.1 Tambah `async def ping(self) -> bool` di `RedisCache` (`app/core/redis_cache.py:97`).
- [x] 2.2 Tambah `async def ping(self) -> bool` di `MongoDBLogger` (`app/services/mongodb_logger.py:155`).
- [x] 2.3 Vector store `_ensure_collection("health_check")` sudah dipakai sebagai liveness probe (existing).

## 3. Endpoint

- [x] 3.1 Update handler `/api/health` di `app/api/routes.py:599-688` agar:
  - Probe semua dependencies (mongo, redis, vector_store, llm) ke `dependencies: Dict[str, str]`.
  - Compose `circuit_breakers = {"llm": breaker.state.value}`.
  - Compute `is_degraded` jika ada dependency != "healthy" atau breaker == "open".
  - Return `JSONResponse(status_code=503, ...)` jika degraded; 200 lainnya. `services` legacy map dipertahankan.

## 4. Tests

- [x] 4.1 `python3 scripts/verify_track_activity_and_health.py` → 11/11 passing termasuk skenario degraded (di env tanpa Redis, status 503 dengan `dependencies.redis="down"` ter-observasi). Existing assertion `status_code in (200, 503)` cover keduanya.

## 5. Verifikasi

- [x] 5.1 `python3 -m py_compile app/api/routes.py app/api/schemas.py app/services/mongodb_logger.py app/core/redis_cache.py` exit 0.
- [x] 5.2 `python3 scripts/verify_track_activity_and_health.py` → all assertions pass; health body includes `dependencies` dan `circuit_breakers` fields.
- [x] 5.3 `openspec validate health-endpoint-degraded-503 --strict` → valid.
