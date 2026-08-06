## 1. Schema

- [x] 1.1 Tambah `TrackActivityRequest` ke `app/api/schemas.py`

## 2. Endpoint

- [x] 2.1 Tambah endpoint `POST /api/track-activity` ke `app/api/routes.py`
- [x] 2.2 Pastikan `get_logic_listener` diimport di routes.py

## 3. Verifikasi

- [x] 3.1 Jalankan `python3 -m py_compile` — syntax OK
- [x] 3.2 Test endpoint via curl — diverifikasi via `scripts/verify_track_activity_and_health.py` (FastAPI TestClient, mock lifespan): `POST /api/track-activity {group_id}` → 200 `{success: true}`; `_last_message_timestamp[group_id]` ter-populate; varian `{group_id, user_id}` juga menambah `_participation_counts[group_id][user_id]`
- [x] 3.3 Verifikasi Logic Listener state — diverifikasi pada langkah 3.2: dict in-memory `_last_message_timestamp` dan `_participation_counts` ter-update sesuai request payload
