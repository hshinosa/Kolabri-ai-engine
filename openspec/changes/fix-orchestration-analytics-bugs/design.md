# Design: Fix Orchestration Analytics Bugs

## Approach

### Bug 1 & 2: CaseID and State Key Mismatch

**Root Cause**: `orchestration.py` receives both `group_id` and `chat_space_id` but uses them inconsistently. Analytics logging uses `chat_space_id` for goal events but `group_id` for message events. State tracking dictionaries keyed by `chat_space_id` but read by `group_id`.

**Fix Strategy**:
- **CaseID**: Use `group_id` consistently for all CaseID fields in `log_activity()` calls. The `chat_space_id` is metadata, not the primary correlation key.
- **State Keys**: Use `group_id` for all state tracking dictionaries (`_group_fading_levels`, `_group_smart_streak`, `_group_message_history`). A group's learning progression should be tracked across all its chat spaces.

**Rationale**: Group-level analytics (learning progression, scaffolding, smart streaks) are pedagogical constructs tied to the student group, not individual chat sessions. Multiple chat spaces within one group (e.g., different discussion topics) should contribute to the same group progression.

### Bug 3: Missing `generate_intervention()` Method

**Root Cause**: `orchestration.py:585-597` calls `self.intervention.generate_intervention()` but `ChatInterventionService` only has `generate_message()` (which is what's actually used elsewhere).

**Fix Strategy**: Two options:
1. **Option A**: Change `orchestration.py` to call existing `generate_message()` method with correct parameters
2. **Option B**: Add `generate_intervention()` wrapper method to `ChatInterventionService` that calls `generate_message()` internally

**Decision**: Option A (fix caller). Simpler, no new code, aligns with existing usage pattern.

**Implementation**:
```python
# Before (orchestration.py:585-597)
intervention_msg = self.intervention.generate_intervention(
    group_id=group_id,
    intervention_type=intervention_type,
    context=orchestration_context
)

# After
intervention_msg = self.intervention.generate_message(
    intervention_type=intervention_type,
    context=orchestration_context,
    group_id=group_id
)
```

### Bug 4: Intervention Type Mismatch

**Root Cause**: `orchestration.py` uses string literals ("low_lexical", "low_quality", "participation_inequity") but `InterventionType` enum defines: redirect, prompt, summarize, clarify, resource, encourage.

**Fix Strategy**: Map orchestration-detected issues to appropriate `InterventionType` values:
- `"low_lexical"` → `InterventionType.PROMPT` (encourage richer vocabulary)
- `"low_quality"` → `InterventionType.CLARIFY` (ask for more detail)
- `"participation_inequity"` → `InterventionType.ENCOURAGE` (prompt quieter members)

**Implementation**: Add mapping function in `orchestration.py`:
```python
def _map_to_intervention_type(self, issue_type: str) -> InterventionType:
    mapping = {
        "low_lexical": InterventionType.PROMPT,
        "low_quality": InterventionType.CLARIFY,
        "participation_inequity": InterventionType.ENCOURAGE,
    }
    return mapping.get(issue_type, InterventionType.PROMPT)
```

## Data Flow (Post-Fix)

```
orchestration.handle_message()
  ├─> log_activity(CaseID=group_id, ...)  # Fixed: all events use group_id
  ├─> _group_fading_levels[group_id]      # Fixed: state keyed by group_id
  ├─> intervention_type = _map_to_intervention_type("low_lexical")
  └─> intervention_msg = self.intervention.generate_message(...)  # Fixed: correct method
```

## Testing Strategy

1. **Unit Tests**: Add test for `_map_to_intervention_type()` with all three issue types
2. **Integration Test**: Mock orchestration call with group having 2 chat spaces, verify:
   - All `log_activity()` calls use same `CaseID` (group_id)
   - State dictionaries updated with `group_id` key
   - Intervention generated without `AttributeError`
   - Intervention type is valid `InterventionType` enum value

## Rollout
- Single PR, merge to main
- No migration needed (in-memory state only)
- No breaking changes (pure bug fixes)
