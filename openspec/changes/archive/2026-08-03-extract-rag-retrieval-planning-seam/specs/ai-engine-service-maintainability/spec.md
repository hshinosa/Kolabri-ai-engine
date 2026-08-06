## ADDED Requirements

### Requirement: RAG retrieval planning is a pure, independently testable seam

The AI engine MUST expose retrieval planning as a pure function that returns a `RetrievalPlan` value object, separate from the async retrieval execution path.

#### Scenario: Plan is computed without I/O

- **WHEN** a caller invokes `build_retrieval_plan(query, query_type, quality_controls)`
- **THEN** the function MUST return a `RetrievalPlan` without performing any vector-store, LLM, or network call

#### Scenario: Plan covers retrieval parameters

- **WHEN** a `RetrievalPlan` is returned
- **THEN** it MUST carry `top_k`, `score_threshold`, `use_reranker`, `rerank_top_n`, and `grounding_threshold` fields

#### Scenario: RAG pipeline consumes the plan

- **WHEN** `RAGPipeline.retrieve(...)` runs
- **THEN** it MUST call `build_retrieval_plan(...)` once and use the returned plan to drive vector-store and reranker calls
