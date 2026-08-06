## Why

`app/services/rag.py` is 615 LOC and mixes two responsibilities: (a) **retrieval planning** — deciding `top_k`, `score_threshold`, and which strategy to use; (b) **retrieval execution** — calling vector store, applying grounding verification, and returning a `RAGResult`. The planning logic is pure, deterministic, and testable in isolation, but today it is entangled with async I/O, making unit tests heavy.

Slice S4 in `improve-ai-engine-testability-and-maintainability` § G calls for extracting the planning seam.

## What Changes

- Add `app/services/rag_retrieval_plan.py` with:
  - `@dataclass RetrievalPlan` carrying `top_k`, `score_threshold`, `use_reranker`, `rerank_top_n`, `grounding_threshold`.
  - Pure function `build_retrieval_plan(query: str, query_type: Literal["factual","conceptual","procedural"] | None, quality_controls) -> RetrievalPlan` that encodes the current planning rules from `rag.py`.
- Update `RAGPipeline.retrieve(...)` to call `build_retrieval_plan(...)` first, then execute against vector store using the resulting plan.
- No behavior change with default settings.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — adds the requirement that retrieval planning is a pure, independently testable seam.

## Impact

- `app/services/rag_retrieval_plan.py` — new file.
- `app/services/rag.py` — calls `build_retrieval_plan(...)` instead of inlining the rules.
- `tests/test_unit/test_rag_retrieval_plan.py` — new file with pure unit tests for each branch of the planning rules.
- RAG benchmark runner output must remain identical when default settings are used.
