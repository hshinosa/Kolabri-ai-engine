# Proposal: Streaming + Socratic Prompt Optimization (PERF-AI-01, PERF-AI-12)

## Problem

Two remaining AI Engine latency items from the performance audit (AUDIT_REPORT_2026-06-19.md):

### PERF-AI-12: Redundant second LLM call on REDIRECT path
**Location:** `app/services/rag.py:527-533`

When the output guardrail detects a direct answer or complete solution (`_contains_direct_answer` / `_contains_complete_solution`), it triggers `GuardrailAction.REDIRECT` → calls `self.llm_service.reframe_to_socratic(llm_response.content)` → **a second full LLM call** to convert the direct answer into Socratic questions.

Root cause: the `SYSTEM_RAG` prompt instructs "Akhiri dengan pertanyaan Socratic" but `COT_RAG_TEMPLATE` instructs "jawab dengan kata-kata yang SAMA dengan konteks" → LLM produces a direct answer → guardrail fires → reframe → 2nd LLM call. The prompt itself invites the behavior the guardrail then corrects.

**Cost:** ~1.5–4s extra latency (full LLM round-trip) on every REDIRECT hit. REDIRECT fires whenever the response contains patterns like "jawabannya adalah", "berikut adalah kodenya:", or large code blocks for homework-flagged queries.

### PERF-AI-01: No streaming for orchestrated chat (high TTFB)
**Location:** `app/api/routes/orchestration.py` (`POST /api/chat`), `app/services/orchestration.py:handle_message`

The orchestrated chat endpoint returns the full response as a single JSON payload after the entire pipeline completes (RAG + grounding + guardrails + intervention check). Time-to-first-byte = full pipeline latency (typically 3–8s). The personal chat endpoint (`POST /chat/personal/stream`) already supports SSE streaming, but the orchestrated path does not.

**Challenge:** Grounding verification (`verify_grounding_async`) and output guardrails (`check_output`) require the **complete** LLM response before they can run. True token-by-token streaming is fundamentally incompatible with post-hoc full-response checks on the FETCH path (hallucination could stream to the user before grounding rejects it).

## Approach

### PERF-AI-12: A+C hybrid (Strengthen prompt, keep reframe as rare fallback)

Strengthen `SYSTEM_RAG` + `COT_RAG_TEMPLATE` + `COT_RAG_WITH_HISTORY` to explicitly forbid direct-answer phrasings and mandate Socratic-first output. This prevents the LLM from producing the patterns that trigger REDIRECT in the first place, eliminating the 2nd call in 90%+ of cases. `reframe_to_socratic()` is **retained** as a safety-net fallback for the rare case where the LLM still emits a direct answer despite the prompt — correct behavior preserved, latency optimized.

**Why not Option B (heuristic reframe, no LLM):** Template-based reframe is not adaptive — it cannot produce context-aware Socratic questions for arbitrary content. Quality regression unacceptable for an academic tool.

**Why not Option C only (merge into single call):** Relying solely on prompt self-correction is brittle; keeping the guardrail + reframe fallback preserves the safety contract.

### PERF-AI-01: C (Conditional streaming — NO_FETCH streams, FETCH stays non-streaming)

Add a streaming path that applies **only** to the NO_FETCH branch (greetings, short follow-ups, acknowledgments — queries that skip retrieval). NO_FETCH has no retrieved context, so grounding verification is not applicable and output guardrails run on the streamed buffer. The FETCH branch (substantive questions — the majority) remains non-streaming because grounding/guardrails need the full response.

**Why not Option A (true streaming + post-verify retract):** Emitting `message_replace` events to swap content the user already saw is a confusing UX and risks briefly exposing hallucinations before retraction. Not acceptable for an academic integrity tool.

**Why not Option B (buffered fake streaming):** No real TTFB improvement — just a visual effect. Reject.

## Scope

### ai-engine
- `app/core/prompt_templates.py` — strengthen `SYSTEM_RAG`, `COT_RAG_TEMPLATE`, `COT_RAG_WITH_HISTORY` (PERF-AI-12)
- `app/services/llm.py` — add `stream_generate()` method wrapping `client.chat.completions.create(stream=True)` (PERF-AI-01)
- `app/services/rag.py` — add `query_stream()` async generator: NO_FETCH path yields tokens from `stream_generate()`; FETCH path delegates to existing `query()` and yields the complete result as a single chunk (PERF-AI-01)
- `app/services/orchestration.py` — add `handle_message_stream()` async generator wrapping `query_stream()` + logging + intervention (PERF-AI-01)
- `app/api/routes/orchestration.py` — add `POST /api/chat/stream` SSE endpoint returning `StreamingResponse` (PERF-AI-01)
- `app/api/schemas.py` — `OrchestrationStreamRequest` (same fields as `OrchestrationRequest`, no response model — SSE) (PERF-AI-01)

### core-api
- `src/services/aiEngine.service.ts` — add `orchestratedChatStream()` that POSTs to `/api/chat/stream` and returns a ReadableStream/async iterator of SSE events (PERF-AI-01)
- `src/socket/index.ts` — in the group chat handler, detect NO_FETCH-eligible queries (greetings/short follow-ups) and use `orchestratedChatStream()` to forward `ai_chunk` events to the room; fall back to `orchestratedChat()` for FETCH queries (PERF-AI-01)

### client-app
- Chat component(s) handling `receive_message` — add `ai_chunk` listener that appends incremental content to a pending AI message bubble; on completion (`ai_done` event), finalize the message (PERF-AI-01)

## Non-Goals
- True token-by-token streaming for the FETCH/RAG path (incompatible with post-hoc grounding)
- Changing the grounding verification algorithm
- Removing `reframe_to_socratic()` (retained as fallback)
- Streaming for intervention messages (interventions are short, generated after main response)

## Risk
- **PERF-AI-12 (Low):** Prompt-only change. `reframe_to_socratic()` fallback preserved, so worst case = current behavior. Existing guardrail tests + RAG tests cover REDIRECT detection.
- **PERF-AI-01 (Medium):** Adds a new SSE endpoint + WebSocket event flow. Conditional branching (NO_FETCH vs FETCH) must correctly classify queries — reuse existing `_should_retrieve()` logic. Client must handle partial state (streaming bubble) + final state (persisted message). Test with integration suite + live chat E2E.
- **Cross-service contract:** New `ai_chunk` / `ai_done` WebSocket events must be handled on client. Backward compat: if client doesn't handle `ai_chunk`, it still receives `receive_message` on completion (fallback emits both).
