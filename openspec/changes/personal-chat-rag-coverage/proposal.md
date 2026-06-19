## Why

Personal-chat RAG silently misses enrolled courses and behaves inconsistently between transport modes. Two concrete defects surfaced while verifying course ingest:

1. `search_personal_rag` hard-slices `course_ids[:10]`, so a student enrolled in more than 10 courses never retrieves from the courses beyond the slice — with no signal that retrieval was incomplete. The cut follows enrollment fetch order, which carries no relevance meaning.
2. The streaming endpoint calls `search_personal_rag` without `provider_context`, while the non-streaming endpoint passes it. When unified-provider embedding is enabled, the two paths embed with different providers and return different retrieval scores for the same query.

## What Changes

- Raise the per-request course scan limit from 10 to 20 so it matches the schema bound (`PersonalChatRequest.course_ids` `max_length=20`), eliminating the silent gap for the supported enrollment range.
- Search the scanned course collections concurrently (`asyncio.gather`) so widening the limit does not multiply latency.
- Pass `provider_context` to `search_personal_rag` from the streaming endpoint, matching the non-streaming endpoint, so both transports embed and retrieve identically.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `rag-grounding-and-correctness`: personal-chat retrieval MUST cover every course the request carries within the schema-supported bound, and retrieval behavior MUST be identical across streaming and non-streaming transports.

## Impact

- Code: `app/api/routes/chat.py` — `search_personal_rag` (scan limit + concurrency) and `personal_chat_stream` (provider_context arg).
- API: no contract change. `course_ids` schema bound (20) already advertised; behavior now honors it.
- Performance: concurrent search keeps added latency near a single-collection round-trip instead of N sequential.
- Out of scope (future work): relevance-ranked course prioritization when enrollment exceeds the scan bound (would require an "active/recent course" signal from core-api). Tracked in design.md as deferred.
