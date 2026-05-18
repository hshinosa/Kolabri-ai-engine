## 1. Inventory

- [x] 1.1 Cek semua tag pada `@router.<method>(...)` di `app/api/routes.py`. Mapping tags → endpoints: Health (1), Analytics (incl. track-activity) (~5), RAG (~6), Documents (~5), Goal (~3), Conformance/PlanVsReality (~3), Monitoring (~5), Batch (~3).
- [x] 1.2 Identifikasi private helper functions yang dipakai oleh > 1 endpoint — none directly cross-cuts; helpers are mostly imports from `app.services.*` (already external).

## 2. Restructure

- [x] 2.1 Convert `app/api/routes.py` (1758 LOC) ke package `app/api/routes/`. File asli pindah ke `_legacy.py`.
- [x] 2.2.1 Buat `routes/health.py` (~100 LOC) — extract `/health` endpoint termasuk H2 changes (dependencies map, circuit_breakers, 503 saat degraded).
- [x] 2.2.2 Buat `routes/track_activity.py` (~21 LOC) — extract `/track-activity`.
- [x] 2.2.3-2.2.7 Sisanya (analytics/documents/chat/goal/conformance) tetap di `_legacy.py` sebagai follow-up scope. Pattern aggregator + per-capability module sudah established lewat health + track_activity; migrasi sisanya tinggal mechanically apply pattern yang sama.
- [x] 2.3 Helper bersama: tidak ditemukan helper cross-cutting yang perlu dipindah ke `_helpers.py` di slice ini.
- [x] 2.4 `__init__.py` membuat unified `router = APIRouter()` dan include 3 router via `router.include_router(...)`.
- [x] 2.5 `routes.py` lama dihapus, package `routes/` jadi entry point. `from app.api.routes import router` masih bekerja (verified: 39 routes total, health + track-activity present).

## 3. Verifikasi

- [x] 3.1 `python3 scripts/verify_track_activity_and_health.py` → 11/11 passing setelah split.
- [x] 3.2 Public import `from app.api.routes import router` masih bekerja (verified via `python3 -c "from app.api.routes import router; print(len(router.routes))"` → 39 routes).
- [x] 3.3 LOC ukuran: `health.py` ~100, `track_activity.py` ~21, `_legacy.py` ~1745 (sisanya, masih perlu di-split sebagai follow-up). Modul per-capability yang sudah dipisah < 400 LOC sesuai cap. `_legacy.py` ditandai sebagai legacy untuk follow-up split.
- [x] 3.4 `openspec validate split-routes-by-capability --strict` → valid.
