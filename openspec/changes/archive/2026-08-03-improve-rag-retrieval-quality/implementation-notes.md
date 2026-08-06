## Implementation Sequencing Notes

### Phase 1 — Retrieval control surface
- Land configurable thresholds and retrieval-count controls in the core RAG path.
- Ensure vector search accepts an explicit score threshold override while preserving current defaults.
- Wire reranker controls into the retrieval path without changing unrelated AI-engine behaviors.

### Phase 2 — Fallback hardening
- Keep vector-search ordering as the fallback path when reranking is unavailable or fails.
- Verify fallback remains deterministic and bounded to the requested output count.
- Preserve existing no-result and no-context handling.

### Phase 3 — Quality evaluation rollout
- Use retrieval quality controls as the runtime configuration contract.
- Use retrieval quality evaluator and review criteria as the approval gate for future tuning changes.
- Expand from unit-level evaluation coverage into curated RAG accuracy suites and benchmark workflows later.

### Suggested next implementation slices
1. Expose runtime retrieval controls through settings and service surfaces.
2. Add benchmark/evaluation dataset plumbing for real Kolabri retrieval cases.
3. Connect review criteria to a repeatable benchmark command or CI gate.
