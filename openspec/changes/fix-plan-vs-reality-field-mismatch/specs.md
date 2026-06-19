# Specs: Fix Plan-vs-Reality Field Mismatch

## SPEC-01: _extract_plan Field Mapping

### Objective
Correctly extract plan (goal) events from MongoDB logs by using the `Activity` field instead of relying on `metadata.phase`.

### Requirements
- Filter events where `Activity` is either `"Goal_Setting"` or `"Goal_Validation"`
- Support backward compatibility with `metadata.phase == "Forethought"` if present
- Extract goal content from appropriate fields:
  - For `Goal_Setting`: use `content` field
  - For `Goal_Validation`: use `Attributes.original_text` field
- Extract `userId` from event
- Extract `Timestamp` for time tracking

### Acceptance Criteria
- ✅ Correctly identifies goal events from realistic MongoDB log data
- ✅ Extracts goal content, user ID, and timestamp
- ✅ Returns empty list when no goal events found
- ✅ Handles both Goal_Setting and Goal_Validation event types

### Implementation Details
```python
goal_events = [
    e for e in events
    if e.get("Activity") in ["Goal_Setting", "Goal_Validation"]
    or e.get("metadata", {}).get("phase") == "Forethought"
]

for event in goal_events:
    # Goal_Setting uses 'content', Goal_Validation uses 'Attributes.original_text'
    content = event.get("content") or event.get("Attributes", {}).get("original_text", "")
    if content:
        goals.append({
            "content": content,
            "timestamp": event.get("Timestamp"),
            "user_id": event.get("userId") or event.get("Resource", "").replace("Student_", "")
        })
```

---

## SPEC-02: _extract_reality Field Mapping

### Objective
Correctly extract reality (message) events from MongoDB logs by using the `Activity` field and normalizing event structure.

### Requirements
- Filter events where `Activity` is `"Student_Message"` or `"Bot_Response"`
- Support backward compatibility with `metadata.interactionType` if present
- Normalize events to ensure `content` field exists:
  - If event lacks `content` field, derive from `Attributes.original_text`
- Preserve original event data via shallow copy

### Acceptance Criteria
- ✅ Correctly identifies student and bot message events
- ✅ Normalizes events with content field
- ✅ Returns empty list when no message events found
- ✅ Maintains original event structure for downstream processing

### Implementation Details
```python
performance_events = [
    e for e in events
    if e.get("Activity") in ["Student_Message", "Bot_Response"]
    or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]
]

normalized_events = []
for e in performance_events:
    normalized = e.copy()
    if "content" not in normalized:
        normalized["content"] = e.get("Attributes", {}).get("original_text", "")
    normalized_events.append(normalized)
```

---

## SPEC-03: _calculate_time_allocation Timestamp Handling

### Objective
Calculate time allocation using the correct `Timestamp` field from MongoDB logs.

### Requirements
- Extract timestamps using `Timestamp` field (capital T) from events
- Fallback to `createdAt` if `Timestamp` not present (backward compatibility)
- Calculate duration in minutes between earliest and latest timestamp
- Return total_minutes = 0 if fewer than 2 timestamps available

### Acceptance Criteria
- ✅ Uses Timestamp field instead of createdAt
- ✅ Handles missing timestamps gracefully
- ✅ Returns correct duration in minutes
- ✅ Returns 0 when insufficient data

### Implementation Details
```python
timestamps = []
for e in events:
    ts = e.get("Timestamp") or e.get("createdAt")
    if ts:
        timestamps.append(ts)

if len(timestamps) < 2:
    return {"total_minutes": 0}

try:
    start_time = min(timestamps)
    end_time = max(timestamps)
    duration_minutes = (end_time - start_time).total_seconds() / 60
except (TypeError, AttributeError):
    return {"total_minutes": 0}
```

---

## SPEC-04: _calculate_session_duration Timestamp Handling

### Objective
Calculate session duration using the correct `timestamp` field (lowercase) from normalized events.

### Requirements
- Extract timestamps using `timestamp` field (lowercase, set by orchestration)
- Fallback to `createdAt` if `timestamp` not present
- Calculate duration in minutes between earliest and latest timestamp
- Return 0.0 if fewer than 2 timestamps available

### Acceptance Criteria
- ✅ Uses timestamp field instead of createdAt
- ✅ Handles missing timestamps gracefully
- ✅ Returns correct duration in minutes
- ✅ Returns 0.0 when insufficient data

### Implementation Details
```python
timestamps = []
for e in events:
    ts = e.get("timestamp") or e.get("createdAt")
    if ts:
        timestamps.append(ts)

if len(timestamps) < 2:
    return 0.0

try:
    start_time = min(timestamps)
    end_time = max(timestamps)
    return (end_time - start_time).total_seconds() / 60
except (TypeError, AttributeError):
    return 0.0
```

---

## SPEC-05: _calculate_engagement_metrics Attributes Field Mapping

### Objective
Calculate engagement metrics using the correct field structure from MongoDB logs (Attributes object).

### Requirements
- HOT percentage: check both `Attributes.is_hot` and `engagement.isHigherOrder` (backward compat)
- Lexical variety: check `Attributes.lexical_variety` first, then `engagement.lexicalVariety`
- Engagement type distribution: use `Attributes.srl_object` first, then `engagement.engagementType`

### Acceptance Criteria
- ✅ Correctly calculates HOT percentage from is_hot field
- ✅ Correctly calculates average lexical variety from lexical_variety field
- ✅ Correctly builds engagement type distribution from srl_object field
- ✅ Maintains backward compatibility with old engagement structure

### Implementation Details
```python
hot_count = sum(
    1 for e in events 
    if e.get("Attributes", {}).get("is_hot") 
    or e.get("engagement", {}).get("isHigherOrder")
)

lexical_varieties = [
    e.get("Attributes", {}).get("lexical_variety") 
    or e.get("engagement", {}).get("lexicalVariety") 
    or 0
    for e in events
]

engagement_types = defaultdict(int)
for e in events:
    eng_type = (
        e.get("Attributes", {}).get("srl_object") 
        or e.get("engagement", {}).get("engagementType") 
        or "behavioral"
    )
    engagement_types[eng_type] += 1
```

---

## SPEC-06: Integration Testing

### Objective
Verify all fixes work together with realistic MongoDB log data.

### Requirements
- Create test fixtures matching actual MongoDB log structure from production
- Test full analyze_session flow end-to-end
- Verify alignment_score > 0 when plan and reality have overlapping topics
- Verify has_plan=True and has_reality=True with proper data

### Acceptance Criteria
- ✅ Integration test passes with realistic event data
- ✅ alignment_score calculated correctly
- ✅ has_plan and has_reality flags set correctly
- ✅ No runtime errors during analysis

### Test Data Structure
```python
events = [
    {
        "CaseID": "group_123_session_1",
        "Activity": "Goal_Setting",
        "Timestamp": "2026-06-19T10:00:00Z",
        "Resource": "Student_user1",
        "metadata": {"interactionType": "GOAL_SETTING", "phase": "Forethought"},
        "content": "Belajar tentang usability testing",
        "userId": "user1"
    },
    {
        "CaseID": "group_123_session_1", 
        "Activity": "Student_Message",
        "Timestamp": "2026-06-19T10:05:00Z",
        "Resource": "Student_user1",
        "Attributes": {
            "original_text": "Usability testing penting untuk UX",
            "srl_object": "Performance",
            "is_hot": True,
            "lexical_variety": 0.8
        }
    }
]
```
