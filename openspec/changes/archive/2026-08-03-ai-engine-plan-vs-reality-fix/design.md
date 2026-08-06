## Context

`orchestration.py` `validate_goal()` (line 208-235) logs goal dengan:
```python
await self.mongo_logger.log_activity({
    "CaseID": f"{chat_space_id}_session_{session_id}",
    "Activity": "Goal_Validation",
    "Attributes": { "original_text": goal_text, "srl_object": "Learning_Goal", ... }
})
```

`plan_vs_reality.py` `_extract_plan()` (line 155-213) mencari:
```python
goal_events = [e for e in events
    if e.get("metadata", {}).get("interactionType") == "GOAL_SETTING"
    or e.get("metadata", {}).get("phase") == "Forethought"]
```

Format tidak cocok — `Activity` vs `metadata.interactionType`, `Attributes` vs `metadata`.

`get_group_analytics()` line 307: `case_id = f"{group_id}_session_1"` — hardcoded.

## Goals / Non-Goals

**Goals:**
- `validate_goal()` log goal dengan format yang dikenali `_extract_plan`
- `get_group_analytics()` pakai session ID dinamis

**Non-Goals:**
- Tidak mengubah `_extract_plan` logic — fix di sisi logging, bukan di sisi reader
- Tidak mengubah format log yang sudah ada — tambah log kedua, jangan hapus yang lama

## Decisions

**D1: Tambah log kedua di validate_goal(), jangan ubah yang lama**
Log pertama (`Activity: "Goal_Validation"`) tetap ada untuk backward compatibility. Tambah log kedua dengan format yang dikenali `_extract_plan`:
```python
await self.mongo_logger.log_activity({
    "CaseID": f"{chat_space_id}_session_{session_id}",
    "Activity": "Goal_Setting",
    "metadata": { "interactionType": "GOAL_SETTING", "phase": "Forethought" },
    "content": goal_text,
    "userId": user_id,
})
```

**D2: Ganti hardcoded session_1 dengan _get_latest_session_id()**
```python
session_id = await self._get_latest_session_id(group_id)
case_id = f"{group_id}_session_{session_id}"
```

## Risks / Trade-offs

- **[Risk] Double logging** → Mitigation: log kedua hanya untuk plan_vs_reality, tidak mempengaruhi proses lain
- **[Risk] _get_latest_session_id() async** → `get_group_analytics()` sudah async, tidak ada masalah

## Open Questions

- None.
