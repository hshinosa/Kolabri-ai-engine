## 1. Fix validate_goal() Log Format

- [x] 1.1 Tambah log kedua di `validate_goal()` dengan format `Activity: "Goal_Setting"`, `metadata.interactionType: "GOAL_SETTING"`, `metadata.phase: "Forethought"`
- [x] 1.2 Log pertama (`Activity: "Goal_Validation"`) tidak diubah

## 2. Fix Hardcoded session_1

- [x] 2.1 Ganti `case_id = f"{group_id}_session_1"` dengan `session_id = await self._get_latest_session_id(group_id)` + `case_id = f"{group_id}_session_{session_id}"`

## 3. Verifikasi

- [x] 3.1 Jalankan `python3 -m py_compile app/services/orchestration.py` — syntax OK
