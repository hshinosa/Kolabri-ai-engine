# Spec: Fix `_extract_reality()` Function

## Overview

Fix `_extract_reality()` to correctly filter Student_Message and Bot_Response events using the `Activity` field instead of `metadata.interactionType`.

## Requirements

### R1: Primary Filter on Activity Field
The function MUST filter events where `Activity in ["Student_Message", "Bot_Response"]` as the primary check.

### R2: Backward Compatibility
The function SHOULD also accept events with `metadata.interactionType in ["STUDENT_MESSAGE", "BOT_RESPONSE"]` for backward compatibility.

### R3: Content Extraction
The function MUST extract message content from `Attributes.original_text` field.

### R4: User ID Extraction
The function MUST extract user ID from `Resource` field (format: `"Student_{user_id}"` or `"Bot"`).

### R5: Metadata Extraction
The function MUST extract metadata from `Attributes` object:
- `is_hot`: Higher-Order Thinking flag
- `lexical_variety`: Lexical diversity score
- `srl_object`: SRL phase (should be "Performance")

### R6: Timestamp Handling
The function MUST extract timestamp from the `Timestamp` field (capital T, ISO format).

## Implementation

**File**: `app/services/plan_vs_reality.py`  
**Function**: `_extract_reality()` (lines 214-267)

### Before
```python
def _extract_reality(self, events):
    performance_events = [
        e for e in events
        if e.get("metadata", {}).get("phase") == "Performance"
        or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]
    ]
    # ... rest of function uses e.get("content") which doesn't exist
```

### After
```python
def _extract_reality(self, events):
    performance_events = [
        e for e in events
        if e.get("Activity") in ["Student_Message", "Bot_Response"]  # Primary
        or e.get("metadata", {}).get("interactionType") in ["STUDENT_MESSAGE", "BOT_RESPONSE"]  # Backward compat
    ]
    
    if not performance_events:
        return {"messages": [], "topics": [], "keywords": [], "time_allocation": {}}
    
    # Extract messages with correct field names
    messages = []
    for event in performance_events:
        attributes = event.get("Attributes", {})
        resource = event.get("Resource", "")
        
        # Extract user_id from Resource field
        user_id = None
        if resource.startswith("Student_"):
            user_id = resource.replace("Student_", "")
        elif resource == "Bot":
            user_id = "ai_assistant"
        
        message = {
            "content": attributes.get("original_text", ""),  # From Attributes
            "user_id": user_id,
            "timestamp": event.get("Timestamp"),  # Capital T
            "is_student": resource.startswith("Student_"),
            "is_hot": attributes.get("is_hot", False),
            "lexical_variety": attributes.get("lexical_variety", 0.0),
            "event_id": event.get("_id")
        }
        if message["content"]:
            messages.append(message)
    
    # Extract topics and keywords
    topics = self._extract_topics_from_messages(messages)
    keywords = self._extract_keywords_from_messages(messages)
    
    # Calculate time allocation
    time_allocation = self._calculate_time_allocation_from_messages(messages)
    
    return {
        "messages": messages,
        "topics": topics,
        "keywords": keywords,
        "time_allocation": time_allocation,
        "message_count": len(messages),
        "student_message_count": sum(1 for m in messages if m["is_student"]),
        "bot_message_count": sum(1 for m in messages if not m["is_student"]),
        "hot_message_count": sum(1 for m in messages if m["is_hot"]),
        "avg_lexical_variety": sum(m["lexical_variety"] for m in messages) / len(messages) if messages else 0.0
    }
```

## Test Cases

### TC1: Extract Reality from Student_Message Event
**Input**:
```python
events = [{
    "CaseID": "group123_session_1",
    "Activity": "Student_Message",
    "Timestamp": "2026-01-20T10:05:00Z",
    "Resource": "Student_user123",
    "Attributes": {
        "original_text": "AI is fascinating because it can learn from data",
        "srl_object": "Performance",
        "is_hot": True,
        "lexical_variety": 0.75
    }
}]
```

**Expected Output**:
```python
{
    "messages": [{
        "content": "AI is fascinating because it can learn from data",
        "user_id": "user123",
        "timestamp": "2026-01-20T10:05:00Z",
        "is_student": True,
        "is_hot": True,
        "lexical_variety": 0.75,
        "event_id": <event_id>
    }],
    "topics": ["AI", "learning", "data"],
    "keywords": ["fascinating", "learn", "data"],
    "time_allocation": {...},
    "message_count": 1,
    "student_message_count": 1,
    "bot_message_count": 0,
    "hot_message_count": 1,
    "avg_lexical_variety": 0.75
}
```

### TC2: Extract Reality from Bot_Response Event
**Input**:
```python
events = [{
    "CaseID": "group123_session_1",
    "Activity": "Bot_Response",
    "Timestamp": "2026-01-20T10:06:00Z",
    "Resource": "Bot",
    "Attributes": {
        "original_text": "Yes, AI uses machine learning algorithms",
        "srl_object": "Performance",
        "is_hot": False,
        "lexical_variety": 0.65
    }
}]
```

**Expected**: Similar structure with `is_student=False`, `user_id="ai_assistant"`.

### TC3: Mixed Events
**Input**: Array with both Student_Message and Bot_Response events  
**Expected**: Correct counts and averages.

### TC4: Empty Events
**Input**: `events = []`  
**Expected**: `{"messages": [], "topics": [], "keywords": [], "time_allocation": {}}`

### TC5: Backward Compatibility
**Input**:
```python
events = [{
    "Activity": "Some_Other",
    "metadata": {"interactionType": "STUDENT_MESSAGE"},
    "content": "Legacy message"
}]
```

**Expected**: Should still extract (backward compat).

## Dependencies

- `_extract_topics_from_messages()` - existing function, no changes needed
- `_extract_keywords_from_messages()` - existing function, no changes needed
- `_calculate_time_allocation_from_messages()` - new helper function (or reuse existing)

## Acceptance Criteria

- [ ] Function filters events by `Activity in ["Student_Message", "Bot_Response"]`
- [ ] Function extracts content from `Attributes.original_text` field
- [ ] Function extracts user_id from `Resource` field
- [ ] Function extracts metadata from `Attributes` object
- [ ] Function extracts timestamp from `Timestamp` field
- [ ] Backward compatibility with `metadata.interactionType` maintained
- [ ] Calculates message counts (total, student, bot, hot)
- [ ] Calculates average lexical variety
- [ ] All test cases pass
- [ ] No regression in existing functionality

## Notes

- Student_Message and Bot_Response events are logged by `mongodb_logger.py:67-88`
- Content is stored in `Attributes.original_text`, not top-level `content`
- Resource field format: `"Student_{user_id}"` for students, `"Bot"` for AI responses
- The `is_hot` flag indicates Higher-Order Thinking (HOT) messages
