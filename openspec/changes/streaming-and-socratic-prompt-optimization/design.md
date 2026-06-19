# Design: Streaming + Socratic Prompt Optimization

## PERF-AI-12: Socratic-First Prompt Strengthening

### Current State

```
SYSTEM_RAG (line 11-24):
  - "Jawab HANYA berdasarkan konteks"
  - "Akhiri dengan pertanyaan Socratic"

COT_RAG_TEMPLATE (line 155-169):
  - "jawab dengan kata-kata dan frasa yang SAMA dengan konteks"
  - "Akhiri dengan pertanyaan Socratic"

guardrails._contains_direct_answer (line 632-640):
  patterns = ["jawabannya adalah", "hasil akhirnya", "berikut adalah kodenya:", "ini jawaban untuk tugas Anda"]
  -> REDIRECT -> reframe_to_socratic() -> 2nd LLM call
```

The prompt instructs the LLM to answer directly using the context's exact words, then the guardrail penalizes direct answers. Contradiction -> wasted LLM call.

### Design: Strengthen SYSTEM_RAG

Add an explicit `LARANGAN JAWABAN LANGSUNG (Socratic-First)` section:
- Forbid opening phrases: "Jawabannya adalah", "Hasil akhirnya"
- Forbid complete solutions for homework; provide skeleton/pseudocode with blanks
- Mandate: explain concept -> let student draw conclusion
- Mandate: end with 1-2 Socratic questions that *guide toward* the answer, not *give* it

### Design: Strengthen COT_RAG_TEMPLATE / COT_RAG_WITH_HISTORY

Modify instruction #2 from "jawab dengan kata-kata yang SAMA" -> "jelaskan konsep dari konteks dengan kata-kata sendiri, JANGAN berikan jawaban siap pakai". Add: "Jika pertanyaan meminta solusi lengkap, berikan kerangka dengan bagian kosong."

### Fallback preserved

`rag.py:527-533` REDIRECT branch + `reframe_to_socratic()` unchanged. If LLM still emits direct-answer patterns despite the strengthened prompt, the guardrail catches it and reframes. Cost: 1 extra call in rare cases. Benefit: safety contract preserved.

### Expected impact

- REDIRECT trigger rate: ~30-50% (current, due to prompt contradiction) -> <10% (after strengthening)
- Average latency on RAG path: -1.5 to -4s in 90%+ of cases (no 2nd call)
- Latency in rare fallback case: unchanged (still 2 calls)

---

## PERF-AI-01: Conditional Streaming (NO_FETCH only)

### Current State

```
Client (WebSocket 'send_message')
  -> core-api/socket/index.ts (handler)
    -> aiEngine.orchestratedChat() (HTTP POST /api/chat, full JSON)
      -> ai-engine orchestration.py handle_message()
        -> rag.query() -> [NO_FETCH: 1 LLM call] | [FETCH: search+rerank+1 LLM call+grounding+guardrail]
      -> return OrchestrationResult (full JSON)
    <- core-api saves ChatLog, emits 'receive_message' (full content)
  <- Client renders complete message
```

TTFB = full pipeline. No incremental feedback.

### Design: Streaming layers

#### Layer 1: LLM service (llm.py)

```python
async def stream_generate(self, prompt, system_prompt, context, temperature, max_tokens):
    """Async generator yielding content chunks (str). Uses stream=True."""
    full_system = system_prompt or self.SYSTEM_PROMPTS["default"]
    if context:
        full_system += f"\n\nKonteks tambahan:\n{context}"
    messages = [{"role": "system", "content": full_system}, {"role": "user", "content": prompt}]
    stream = await self.client.chat.completions.create(
        model=self.model, messages=messages,
        temperature=temperature or self.temperature,
        max_tokens=max_tokens or self.max_tokens,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content
```

Note on retry/circuit-breaker: streaming path bypasses tenacity/circuit-breaker wrapping (those wrap `_execute_with_retry` which expects a complete response). Rationale: streaming is fire-and-forget; if the stream fails mid-way, the caller catches and emits an error event. Adding tenacity to a streaming generator is complex (can't retry after partial yield) and the NO_FETCH path is low-risk (no grounding at stake). Acceptable tradeoff; documented.

#### Layer 2: RAG pipeline (rag.py)

```python
async def query_stream(self, query, collection_name, chat_history, ...):
    """Async generator. NO_FETCH: stream tokens. FETCH: delegate to query(), yield full answer as single chunk + metadata."""
    should_fetch = self._should_retrieve(search_query, self._last_contexts)
    if not should_fetch:
        async for chunk in self.llm_service.stream_generate(...):
            yield {"type": "token", "content": chunk}
        yield {"type": "done", "sources": [], "citations": []}
    else:
        result = await self.query(query, collection_name, ...)
        yield {"type": "full", "content": result.answer, "sources": result.sources, ...}
        yield {"type": "done", ...}
```

#### Layer 3: Orchestrator (orchestration.py)

```python
async def handle_message_stream(self, user_id, group_id, message, topic, **kwargs):
    """Async generator wrapping query_stream + logging + intervention."""
    async for event in self.rag.query_stream(query=message, ...):
        if event["type"] == "token":
            yield event
        elif event["type"] in ("full", "done"):
            # run logging + intervention check, then yield
            yield event
```

#### Layer 4: Route (orchestration.py route)

```python
@router.post("/chat/stream")
async def orchestrated_chat_stream(request: OrchestrationRequest):
    orchestrator = get_orchestrator(...)
    async def event_generator():
        try:
            async for event in orchestrator.handle_message_stream(...):
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Internal error'})}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

#### Layer 5: core-api consumer (aiEngine.service.ts)

```typescript
async *orchestratedChatStream(request: OrchestrationRequest): AsyncGenerator<StreamEvent> {
    const response = await fetch(`${this.baseUrl}/api/chat/stream`, {
        method: 'POST', headers: this.getHeaders(), body: JSON.stringify(request),
    });
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') return;
                yield JSON.parse(data);
            }
        }
    }
}
```

#### Layer 6: core-api socket handler (socket/index.ts)

Decision point: the socket handler must decide whether to use streaming or the existing full-response path. Reuse `_should_retrieve()` classification by mirroring its logic (short query / greeting -> NO_FETCH -> stream; else -> full).

```typescript
const isStreamEligible = isNoFetchEligible(question); // mirrors SKIP_PATTERNS + MIN_QUERY_WORDS
if (isStreamEligible && isAvailable) {
    let fullContent = '';
    try {
        for await (const event of aiEngineService.orchestratedChatStream(request)) {
            if (event.type === 'token') {
                fullContent += event.content;
                io.to(roomId).emit('ai_chunk', { chatSpaceId, content: event.content, timestamp: ... });
            } else if (event.type === 'full') {
                fullContent = event.content;
                io.to(roomId).emit('ai_chunk', { chatSpaceId, content: event.content, replace: true, ... });
            } else if (event.type === 'done') {
                // Save ChatLog with fullContent, emit receive_message (final), emit ai_done
                io.to(roomId).emit('ai_done', { chatSpaceId, messageId: ..., citations: ... });
            }
        }
    } catch (e) {
        io.to(roomId).emit('ai_chunk', { chatSpaceId, content: 'Maaf, terjadi kesalahan.', replace: true });
        io.to(roomId).emit('ai_done', { chatSpaceId, error: true });
    }
} else {
    // Existing full-response path (FETCH)
}
```

Backward compat: on stream completion, the handler still saves a `ChatLog` and emits `receive_message` (the full, final message). Clients that don't implement `ai_chunk` will simply render the complete message when `receive_message` fires -- identical to current behavior. Clients that do implement `ai_chunk` get incremental UX.

#### Layer 7: client-app

Add `ai_chunk` + `ai_done` event listeners in the group chat component. On `ai_chunk`: if no pending AI bubble exists, create one; append `content` (or replace if `replace: true`). On `ai_done`: mark bubble as complete, attach `messageId` + citations. On `receive_message` for the same `chatSpaceId` + AI sender: if a pending bubble exists and content matches, skip duplicate render (the stream already showed it).

### NO_FETCH eligibility classification

Mirror `rag.py:_should_retrieve()` logic in core-api. Classification rules:
- Query lower-cased in SKIP_PATTERNS (halo, hai, ok, terima kasih, etc.) -> NO_FETCH
- Word count < 3 -> NO_FETCH
- Greeting prefix + <=5 words -> NO_FETCH
- Else -> FETCH (non-streaming)

### Timeout handling

- ai-engine: `stream_generate` uses the existing httpx client timeout (connect + read=45s after PERF-AI-07). Stream chunks should arrive well within read timeout.
- core-api: `orchestratedChatStream` fetch uses `fetchWithTimeout` with `LLM_TIMEOUT`. SSE keepalive: if no chunk for 30s, abort + emit error.
- orchestration route: no `asyncio.wait_for` wrapper on stream (would cancel the generator mid-stream). Rely on httpx timeout + client abort.

### What stays non-streamed

- FETCH path (grounding + guardrails need full response)
- Intervention generation (short, post-main-response)
- Personal chat `/chat/personal/stream` (already streams, unchanged)
- Summary generation, goal validation (separate endpoints, not chat)

### Test strategy

- Unit: `test_stream_generate` (mock AsyncOpenAI stream), `test_query_stream_no_fetch` (assert token yields), `test_query_stream_fetch_fallback` (assert single full chunk), `test_handle_message_stream` (assert event sequence)
- Integration: `test_orchestration_stream_route` (SSE format, [DONE] terminator, error handling)
- core-api: `test_aiEngine_orchestratedChatStream` (SSE parsing), `test_socket_ai_chunk_emit` (NO_FETCH path emits ai_chunk + receive_message)
- E2E (manual, live): send greeting in group chat -> observe incremental render; send substantive question -> observe full render (no chunks)
