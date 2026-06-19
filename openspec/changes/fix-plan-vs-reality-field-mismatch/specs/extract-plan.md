# Spec: Fix `_extract_plan()` Function

## Overview

Fix `_extract_plan()` to correctly filter Goal_Setting events using the `Activity` field instead of relying solely on `metadata.interactionType`.

## Requirements

### R1: Primary Filter on Activity Field
The function MUST filter events where `Activity == "Goal_Setting"` as the primary check.

### R2: Backward Compatibility
The function SHOULD also accept events with `metadata.interactionType == "GOAL_SETTING"` for backward compatibility with any legacy logs.

### R3: Content Extraction
The function MUST extract goal content from the `content` field (not `Attributes.original_text`).

### R4: User ID Extraction  
The function MUST extract user ID from the `userId` field.

### R5: Timestamp Handling
The function MUST extract timestamp from the `Timestamp` field (capital T, ISO format).

## Implementation

**File**: `app/services/plan_vs_reality.py`  
**Function**: `_extract_plan()` (lines 152-212)

### Before
```python
def _extract_plan(self, events):
    goal_events = [
        e for e in events
        if e.get("metadata", {}).get("interactionType") == "GOAL_SETTING"
        or e.get("metadata", {}).get("phase") == "Forethought"
    ]
    # ... rest of function
```

### After
```python
def _extract_plan(self, events):
    goal_events = [
        e for e in events
        if e.get("Activity") == "Goal_Setting"  # Primary: use Activity field
        or e.get("metadata", {}).get("interactionType") == "GOAL_SETTING"  # Backward compat
    ]
    
    if not goal_events:
        return {"goals": [], "topics": [], "keywords": [], "time_allocation": {}}
    
    # Extract goals with correct field names
    goals = []
    for event in goal_events:
        goal = {
            "content": event.get("content", ""),  # Use content field
            "user_id": event.get("userId"),  # Use userId field
            "timestamp": event.get("Timestamp"),  # Use Timestamp field (capital T)
            "event_id": event.get("_id")
        }
        if goal["content"]:
            goals.append(goal)
    
    # Extract topics and keywords
    topics = self._extract_topics_from_goals(goals)
    keywords = self._extract_keywords_from_goals(goals)
    
    # Calculate time allocation
    time_allocation = self._calculate_time_allocation(goal_events)
    
    return {
        "goals": goals,
        "topics": topics,
        "keywords": keywords,
        "time_allocation": time_allocation
    }
```

## Test Cases

### TC1: Extract Plan from Goal_Setting Event
**Input**:
```python
events = [{
    "CaseID": "group123_session_1",
    "Activity": "Goal_Setting",
    "Timestamp": "2026-01-20T10:00:00Z",
    "Resource": "Student_user123",
    "metadata": {"interactionType": "GOAL_SETTING", "phase": "Forethought"},
    "content": "Learn about AI fundamentals",
    "userId": "user123"
}]
```

**Expected Output**:
```python
{
    "goals": [{
        "content": "Learn about AI fundamentals",
        "user_id": "user123",
        "timestamp": "2026-01-20T10:00:00Z",
        "event_id": <event_id>
    }],
    "topics": ["AI", "fundamentals"],
    "keywords": ["learn", "ai", "fundamentals"],
    "time_allocation": {...}
}
```

### TC2: Empty Events
**Input**: `events = []`  
**Expected**: `{"goals": [], "topics": [], "keywords": [], "time_allocation": {}}`

### TC3: No Goal_Setting Events
**Input**: `events = [{"Activity": "Student_Message", ...}]`  
**Expected**: `{"goals": [], "topics": [], "keywords": [], "time_allocation": {}}`

### TC4: Backward Compatibility
**Input**:
```python
events = [{
    "Activity": "Some_Other",
    "metadata": {"interactionType": "GOAL_SETTING"},
    "content": "Legacy goal"
}]
```

**Expected**: Should still extract the goal (backward compat).

## Dependencies

- `_extract_topics_from_goals()` - existing function, no changes needed
- `_extract_keywords_from_goals()` - existing function, no changes needed
- `_calculate_time_allocation()` - will be fixed in separate spec

## Acceptance Criteria

- [ ] Function filters events by `Activity == "Goal_Setting"`
- [ ] Function extracts content from `content` field
- [ ] Function extracts user_id from `userId` field
- [ ] Function extracts timestamp from `Timestamp` field
- [ ] Backward compatibility with `metadata.interactionType` maintained
- [ ] All test cases pass
- [ ] No regression in existing functionality

## Notes

- Goal_Setting events are logged by `orchestration.py:451-462`
- The event structure includes both `Activity` field and `metadata` object
- Content is stored directly in event, not in `Attributes`
