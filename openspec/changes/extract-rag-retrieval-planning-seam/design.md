## Context

`rag.py:97-98` reads `quality_controls.semantic_cache_threshold` and `quality_controls.grounding_threshold` once at construction. The `score_threshold` argument is later optionally overridden per call (`rag.py:175`, `rag.py:197`, `rag.py:274`). The "plan" today is implicit — distributed across `__init__`, `retrieve()`, and `_query_with_plan()`. Pulling it into a named, pure function makes each branch testable without a vector store or LLM.

## Goals / Non-Goals

**Goals:**
- A single function that, given (query, query_type, quality_controls), returns a deterministic `RetrievalPlan`.
- Pure: no I/O, no global state.
- Trivially unit-testable: a test calls `build_retrieval_plan(...)` and asserts the dataclass fields.

**Non-Goals:**
- Tuning planning rules.
- Replacing `quality_controls`.
- Touching grounding execution itself (still in `rag.py`).

## Decisions

### D1: Plan is a frozen dataclass
`@dataclass(frozen=True)` so the planner cannot mutate it during execution. Forces any "plan adjustment" to produce a new plan, which is easier to follow.

### D2: Plan does not own the query
The plan is what to do, not what is being asked. Caller still owns the query string. This keeps the dataclass small.

### D3: Query-type detection stays in caller
If the AI engine ever adds an automatic query-type classifier, it lives in its own module and feeds `query_type` into the plan builder. The plan builder itself does not classify.

## Risks / Trade-offs

- **Risk: rag.py rules are subtly stateful** — a search must confirm no `self.*` state mutation inside the planning portion. Mitigation: dry-run the extraction by reading the planning-related lines before extracting.
- **Risk: existing caching / semantic-similarity gate may be tangled with planning** — Mitigation: keep cache gate in `RAGPipeline.retrieve(...)`; the plan only covers retrieval-execution parameters.

## Open Questions

- None.
