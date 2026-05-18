## Why

`plan_vs_reality.py` tidak pernah menemukan data "plan" karena dua bug:

1. **Format mismatch**: `_extract_plan()` mencari events dengan `metadata.interactionType == "GOAL_SETTING"` atau `metadata.phase == "Forethought"`. Tapi `orchestrator.validate_goal()` me-log goal dengan format `Activity: "Goal_Validation"`, `Attributes.srl_object: "Learning_Goal"` — tidak ada field `metadata.interactionType` atau `metadata.phase`. Hasilnya `has_plan: False` selalu.

2. **Hardcoded session_1**: `get_group_analytics()` line 307 menggunakan `case_id = f"{group_id}_session_1"` — hardcoded. Selalu lihat session 1, bukan session aktif. Seharusnya pakai `await self._get_latest_session_id(group_id)`.

## What Changes

- `validate_goal()` di `orchestration.py`: tambah log event kedua dengan format yang dikenali `_extract_plan` — `metadata.interactionType: "GOAL_SETTING"`, `metadata.phase: "Forethought"`, `content: goal_text`
- `get_group_analytics()` di `orchestration.py`: ganti `session_1` hardcoded dengan `await self._get_latest_session_id(group_id)`

## Capabilities

### Modified Capabilities

- `plan-vs-reality-analysis`: Plan extraction sekarang menemukan goal events karena format log sudah sesuai. Session ID sekarang dinamis, bukan hardcoded.

## Impact

- `app/services/orchestration.py` — 2 perubahan kecil
