# Proposal: Fix Orchestration Analytics Bugs

## Problem
Four critical bugs discovered in `orchestration.py` that break group discussion analytics, intervention generation, and teacher notification:

1. **CaseID Mismatch** — `Goal_Setting`/`Goal_Validation` use `chat_space_id`, `Student_Message`/`Bot_Response` use `group_id`. Analytics cannot correlate plan vs reality across sessions.

2. **State Tracking Key Mismatch** — `_group_fading_levels`/`_group_smart_streak` written keyed by `chat_space_id` (lines 418-429) but read by `group_id` (line 94). Complete read/write mismatch for groups with multiple chat spaces.

3. **Missing `generate_intervention()` Method** — `orchestration.py:585-597` calls `self.intervention.generate_intervention()` but method doesn't exist in `ChatInterventionService`. Will `AttributeError` crash when intervention triggered.

4. **Intervention Type Mismatch** — orchestration uses string types ("low_lexical", "low_quality", "participation_inequity") not in `InterventionType` enum (redirect, prompt, summarize, clarify, resource, encourage).

## Scope
- `app/services/orchestration.py` — CaseID + state key fixes
- `app/services/intervention.py` — add `generate_intervention()` or fix caller
- `app/services/orchestration.py` — align intervention type strings to enum

## Non-Goals
- Dead code removal of `logic_listener.check_silence`/`check_relevance` (separate proposal)
- WebSocket push notifications (core-api responsibility)
- Engagement data persistence to ChatLog (core-api responsibility)

## Risk
- **Low**: Pure bug fixes, no new features. Existing test coverage should catch regressions.
- **Medium**: Intervention method addition requires understanding intended contract (generate structured message from type + context).
