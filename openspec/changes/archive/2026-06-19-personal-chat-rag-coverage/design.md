## Context

`search_personal_rag` (`app/api/routes/chat.py`) merges retrieval across a student's enrolled course collections for personal chat. Collections are named `course_{course_id}` (UUID). Two defects exist:

- Line 246: `for course_id in course_ids[:10]` caps the scan at 10, while `schemas.py` advertises `course_ids` up to `max_length=20`. Students enrolled in >10 courses lose retrieval for the overflow, silently.
- Line 400 (`personal_chat_stream`) calls `search_personal_rag(message, course_ids)` with no `provider_context`; line 330 (`personal_chat`) passes `resolved_ctx`. With `UNIFIED_PROVIDER_PERSONAL_CHAT` enabled, the two transports embed via different providers → divergent retrieval. The flag is currently off, so the bug is latent but real.

The scan loop is sequential; naively raising the cap to 20 would roughly double worst-case retrieval latency.

## Goals / Non-Goals

**Goals:**
- Scan up to the schema bound (20) instead of 10.
- Keep latency bounded when scanning more collections (concurrency).
- Make streaming and non-streaming retrieval use the same provider context.

**Non-Goals:**
- Relevance-based course prioritization when enrollment exceeds the scan bound (A2 — deferred, see Open Questions).
- Changing collection naming, ingest, or the `course_ids` schema bound itself.
- Any change to grounding, citation formatting, or scoring thresholds.

## Decisions

**D1 — Raise scan cap to the schema bound, not unbounded.**
Use `course_ids[:20]` (or reference the schema's `max_length`) rather than removing the slice. The schema already caps the input at 20; honoring that bound keeps retrieval cost bounded and aligns code with the advertised contract. Alternative (no slice) rejected: an unvalidated caller could pass an arbitrarily large list and blow up latency/fan-out.

**D2 — Concurrent collection search via `asyncio.gather`.**
Replace the sequential `for` loop with concurrent per-collection searches gathered together, preserving the existing merge (`sort by score`, `top-7`) and per-collection error isolation (a failing collection logs `personal_rag_collection_skip` and contributes nothing). Alternative (sequential, raised cap) rejected: latency scales linearly with course count; concurrency keeps it near one round-trip.

**D3 — Pass `provider_context` from the streaming endpoint.**
`personal_chat_stream` resolves provider context for the LLM already (line 390-393); reuse the same resolved context for `search_personal_rag`, matching `personal_chat`. One-line parity fix. Alternative (leave as-is) rejected: latent divergence the moment unified-provider embedding is enabled.

## Risks / Trade-offs

- [Concurrent fan-out raises peak load on Qdrant per request] → Bounded by the cap of 20 and existing `n_results=3` / `score_threshold=0.35`; Qdrant handles concurrent point searches comfortably at this scale (collections hold 6–198 points).
- [Per-collection exceptions inside `gather`] → Use `return_exceptions=True` (or per-task try/except) so one failing collection cannot abort the whole batch; preserve the existing skip-and-log behavior.
- [Behavior change is silent to callers] → No API contract change; covered by spec scenarios and unit tests asserting all requested collections are searched.

## Migration Plan

1. Edit `search_personal_rag` (cap + concurrency) and `personal_chat_stream` (provider_context arg).
2. Add unit tests: (a) >10 course_ids → all collections searched; (b) one failing collection isolated; (c) streaming passes provider_context.
3. Deploy: rebuild + recreate `ai-engine` container on VPS; verify via direct `search_personal_rag` call and a live chat.
4. Rollback: revert the single-file change and rebuild; no data or schema migration involved.

## Open Questions

- **A2 (deferred future work): course prioritization beyond the scan bound.** When a student is enrolled in more than 20 courses, which subset should be scanned? Requires a relevance/recency signal (e.g., "active course" or "recently accessed") supplied by core-api. Out of scope here; the 20-course bound covers the current enrollment range. Tracked as a follow-up change.
