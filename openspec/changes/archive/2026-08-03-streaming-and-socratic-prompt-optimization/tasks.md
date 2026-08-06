# Tasks: Streaming + Socratic Prompt Optimization

## PERF-AI-12: Strengthen Socratic-First Prompt

- [x] T1: Strengthen `SYSTEM_RAG` in `app/core/prompt_templates.py` — add `LARANGAN JAWABAN LANGSUNG (Socratic-First)` section forbidding "Jawabannya adalah", "Hasil akhirnya"; mandate concept-then-Socratic-question format
- [x] T2: Strengthen `COT_RAG_TEMPLATE` — change instruction #2 from "jawab dengan kata-kata yang SAMA" to "jelaskan konsep dengan kata-kata sendiri, JANGAN jawaban siap pakai"; add skeleton-with-blanks instruction for code requests
- [x] T3: Strengthen `COT_RAG_WITH_HISTORY` — same anti-direct-answer instruction as T2
- [x] T4: Verify `reframe_to_socratic()` in `llm.py:309-316` and REDIRECT branch in `rag.py:527-533` remain unchanged (fallback preserved)
- [x] T5: Run ai-engine test suite — confirm no prompt-dependent test regressions (guardrail tests, RAG tests, orchestration coverage)

## PERF-AI-01: Conditional Streaming (NO_FETCH)

### ai-engine
- [x] T6: Add `stream_generate()` async generator to `OpenAILLMService` in `app/services/llm.py` — wraps `client.chat.completions.create(stream=True)`, yields content chunks
- [x] T7: Add `query_stream()` async generator to `RAGPipeline` in `app/services/rag.py` — NO_FETCH path calls `stream_generate()` and yields `{"type":"token","content":chunk}`; FETCH path delegates to existing `query()` and yields `{"type":"full",...}` then `{"type":"done",...}`
- [x] T8: Add `handle_message_stream()` async generator to `Orchestrator` in `app/services/orchestration.py` — wraps `query_stream()`, runs logging + intervention on completion, yields events
- [x] T9: Add `POST /api/chat/stream` SSE endpoint in `app/api/routes/orchestration.py` — returns `StreamingResponse` with `text/event-stream`, emits `data: {json}\n\n` per event + `data: [DONE]\n\n` terminator
- [x] T10: Write unit tests — `test_stream_generate` (mock stream), `test_query_stream_no_fetch`, `test_query_stream_fetch_fallback`, `test_handle_message_stream_event_sequence`
- [x] T11: Write integration test — `test_orchestration_stream_route` (SSE format, [DONE] terminator, error event on exception)

### core-api
- [x] T12: Add `orchestratedChatStream()` async generator to `AIEngineService` in `src/services/aiEngine.service.ts` — POSTs to `/api/chat/stream`, parses SSE, yields `{type, content, ...}` events
- [x] T13: Add `isNoFetchEligible()` helper in `src/socket/index.ts` (or utils) — mirrors `rag.py:_should_retrieve()` SKIP_PATTERNS + MIN_QUERY_WORDS logic
- [x] T14: Modify group chat `send_message` handler in `src/socket/index.ts` — if `isNoFetchEligible(question) && isAvailable`: use `orchestratedChatStream()`, emit `ai_chunk` events per token, save ChatLog on done, emit `receive_message` (final) + `ai_done`; else: existing `orchestratedChat()` path
- [x] T15: Write tests — `test_aiEngine_orchestratedChatStream` (SSE parsing), `test_socket_ai_chunk_emit` (NO_FETCH path emits ai_chunk + receive_message + ai_done)

### client-app
- [x] T16: Add `ai_chunk` + `ai_done` socket event listeners in group chat component — on `ai_chunk`: create/append pending AI bubble; on `ai_done`: finalize bubble with messageId + citations; on `receive_message`: skip duplicate if pending bubble exists with matching content

## Verification & Deploy
- [x] T17: Run full ai-engine test suite (`pytest -q --tb=no`)
- [x] T18: Run full core-api test suite (`npx vitest run --reporter=dot`)
- [x] T19: Build core-api (`npm run build`) + check client-app TS (`npx tsc --noEmit`)
- [x] T20: Commit atomically per repo
- [x] T21: Sync to VPS + rebuild containers (`docker compose build ai-engine core-api client-app && up -d`)
- [x] T22: Verify live — 8 containers healthy, web 200, API 200; manual E2E: greeting in group chat (streaming) + substantive question (non-streaming)
