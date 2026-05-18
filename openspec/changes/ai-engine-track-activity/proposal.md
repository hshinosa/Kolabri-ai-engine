## Why

Core API's socket handler needs to notify AI Engine when a group message is sent so Logic Listener can track group activity for silence detection. Currently no lightweight endpoint exists for this — the only way to update Logic Listener's state is via `/api/chat` which triggers full LLM orchestration. A dedicated lightweight endpoint is needed that just updates the timestamp without generating any response.

## What Changes

- Add `POST /api/track-activity` endpoint to AI Engine
- Endpoint calls `logic_listener.update_last_message_time(group_id)` only — no LLM, no analytics, no response generation
- Protected by `X-API-Key` header (CORE_API_SECRET)
- Returns `{"success": true}` immediately

## Capabilities

### New Capabilities

- `track-activity-endpoint`: Lightweight endpoint for Core API to notify AI Engine of group activity. Updates Logic Listener's `_last_message_timestamp` so silence detection works for all groups, not just those using @AI.

### Modified Capabilities

<!-- None -->

## Impact

- `app/api/routes.py` — add `POST /api/track-activity` endpoint
- `app/api/schemas.py` — add `TrackActivityRequest` schema (`group_id: str`)
