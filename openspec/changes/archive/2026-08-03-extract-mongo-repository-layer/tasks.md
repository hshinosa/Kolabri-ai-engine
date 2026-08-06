## 1. Inventory

- [x] 1.1 `rtk grep -n "activity_logs\." app/` — ditemukan 8 call site di `orchestration.py:366,372,374`, `export_service.py:49,112,292`, `mongodb_logger.py:51,52,79,121`. Slice ini mencakup orchestration (3 call) + repository foundation; export_service migrasi adalah follow-up scope karena mengandung field projection yang lebih kaya.

## 2. Implementation

- [x] 2.1 Buat package `app/services/repositories/__init__.py` re-export `ActivityLogRepository`.
- [x] 2.2 Buat `activity_log_repository.py` dengan 3 method async: `get_latest_session_for_group(group_id)`, `get_last_intervention_for_group(group_id)`, `get_first_student_message_after(group_id, timestamp)`. Constructor menerima `db: Any` (Motor `AsyncIOMotorDatabase`).
- [x] 2.3 Refactor `orchestration.py:_get_latest_session_id` (line 366) — instantiate `ActivityLogRepository(self.mongo_logger.db)` dan panggil `get_latest_session_for_group(group_id)`.
- [x] 2.4 Refactor `orchestration.py:_calculate_intervention_impact` (lines 372, 374) — pakai `get_last_intervention_for_group` + `get_first_student_message_after`.
- [x] 2.5 `plan_vs_reality.py` dan `process_mining_anomaly.py` tidak punya direct `activity_logs.find` call (verified via grep) — mereka pakai `mongo_logger.get_activity_logs` yang sudah abstrak. Tidak perlu refactor.

## 3. Tests

- [x] 3.1 Buat `tests/test_unit/test_activity_log_repository.py` — 5 test: extract session id, return None saat empty, query shape last_intervention, timestamp filter, db=None safe path. Pakai `unittest.mock.AsyncMock`.

## 4. Verifikasi

- [x] 4.1 `pytest tests/test_unit/test_activity_log_repository.py -v` → 5 passed.
- [x] 4.2 `python3 -m py_compile app/services/orchestration.py app/services/repositories/*.py` exit 0.
- [x] 4.3 `openspec validate extract-mongo-repository-layer --strict` → valid.
