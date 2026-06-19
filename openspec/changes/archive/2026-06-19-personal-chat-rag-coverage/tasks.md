## 1. Implementation

- [x] 1.1 In `app/api/routes/chat.py`, change `search_personal_rag` scan from `course_ids[:10]` to the schema bound (20), searching collections concurrently with `asyncio.gather` (return_exceptions or per-task try/except), preserving the existing per-collection skip-and-log, score sort, and top-7 merge.
- [x] 1.2 In `personal_chat_stream`, pass the already-resolved `provider_context` into `search_personal_rag` so streaming matches non-streaming retrieval.

## 2. Tests

- [x] 2.1 Add a unit test asserting that with 15 course IDs, `search_personal_rag` issues a search for all 15 collections (mock vector_store.search; assert call count / collection names), not just 10.
- [x] 2.2 Add a unit test asserting a single failing collection is isolated (one mocked search raises) and the remaining results are still merged and returned.
- [x] 2.3 Add a unit test asserting `personal_chat_stream` invokes `search_personal_rag` with a non-None `provider_context` (parity with `personal_chat`).

## 3. Verification

- [x] 3.1 Run the new tests: `python3 -m pytest tests/test_unit -q --tb=no -k "personal_rag or rag_coverage"`.
- [x] 3.2 Rebuild + recreate the `ai-engine` container on VPS; confirm healthy.
- [x] 3.3 Smoke test: direct `search_personal_rag` call for a course beyond the old 10-slice returns citations; one live personal chat returns a grounded reply with citations.
