# Changelog

## [1.1.0] - 2026-05-01

### Added
- Output grounding verification (`app/services/grounding_verifier.py`)
- Socratic scaffolding filter (`app/services/socratic_filter.py`)
- Gini coefficient normalization in logic listener
- SRL phase classification (`app/services/srl_classifier.py`)
- XES export format (`app/services/xes_exporter.py`)
- RAG-Token multi-source behavior in RAG pipeline
- Prompt injection detector (`app/services/injection_detector.py`)
- Toxicity scorer (`app/services/toxicity_scorer.py`)
- PII detector with masking (`app/services/pii_detector.py`)
- Conformance checker with token replay/alignment scoring (`app/services/conformance_checker.py`)
- 7 new API endpoints for Core API integration:
  - `POST /api/chat` (orchestrated chat)
  - `POST /api/intervention/analyze`
  - `POST /api/intervention/summary`
  - `POST /api/intervention/prompt`
  - `GET /api/analytics/group/{group_id}`
  - `GET /api/analytics/export`
  - `DELETE /api/documents/{document_id}`
- Locust load testing suite (`benchmarks/locustfile.py`)
- pytest-benchmark performance tests (`tests/test_benchmarks/`)
- GitHub Actions CI workflow

### Changed
- Merged `*_optimized.py` services into regular versions (-1067 lines)
- Added connection pooling (httpx.AsyncClient) to LLM service
- `OPENAI_API_KEY` and `CORE_API_SECRET` now have empty defaults for non-production environments
- Fixed circular import in `app/services/__init__.py` (lazy init)
- RAGResult fields are additive only (backward compatible)

### Fixed
- 187 test errors + 74 failures resolved (VISION_AVAILABLE, embedding imports, intervention methods, cosine similarity)
- 6 skipped PIL tests fixed with FakeImage mock
- Health check endpoint now properly mocks local LLM import
- `httpx[http2]` added to requirements for HTTP/2 support

### Testing
- Unit tests: 54 → 1719 (98.15% coverage)
- Key coverage: routes.py 98%, batch_routes.py 96%, config.py 99%, llm.py 99%
- Performance benchmarks: guardrails pipeline 91K ops/sec, injection detection 107K ops/sec
