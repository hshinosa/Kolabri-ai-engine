## 1. Discovery

- [x] 1.1 Baca `app/services/rag.py` lines 80–340 + `app/services/rag_quality.py`. Existing `RetrievalSearchPlan` di `rag_quality.py` sudah punya partial seam (output_n_results, search_n_results, score_threshold, reranking_enabled). Slice ini menambah `RetrievalPlan` baru yang spec-compliant: `top_k`, `score_threshold`, `use_reranker`, `rerank_top_n`, `grounding_threshold`, plus per-query-type rules.

## 2. Implementation

- [x] 2.1 Buat `app/services/rag_retrieval_plan.py` dengan `@dataclass(frozen=True) RetrievalPlan` (5 fields per spec).
- [x] 2.2 Implementasi `build_retrieval_plan(query, query_type, quality_controls, requested_n_results=None, requested_score_threshold=None) -> RetrievalPlan` — pure function, no I/O. Per-type rules: factual (tighten threshold + cap rerank to 3), conceptual (loosen threshold by 0.05), procedural (cap rerank to 3).
- [x] 2.3 Refactor `RAGPipeline.retrieve(...)` di `app/services/rag.py:268-323` untuk panggil `build_retrieval_plan(...)` dan pakai `plan.top_k`, `plan.score_threshold`, `plan.use_reranker`, `plan.rerank_top_n`. Output truncation pakai `n_results or self.quality_controls.top_k_results`.

## 3. Tests

- [x] 3.1 Buat `tests/test_unit/test_rag_retrieval_plan.py` dengan 6 test: default plan saat `query_type=None`, factual tightens threshold + caps rerank, conceptual loosens threshold, procedural caps rerank, plan adalah pure function (deterministic), requested overrides propagate.

## 4. Verifikasi

- [x] 4.1 `pytest tests/test_unit/test_rag_retrieval_plan.py tests/test_integration/test_rag_pipeline.py -v` → 10 passed.
- [x] 4.2 `python3 -m py_compile app/services/rag.py app/services/rag_retrieval_plan.py` exit 0.
- [x] 4.3 `openspec validate extract-rag-retrieval-planning-seam --strict` → valid.
