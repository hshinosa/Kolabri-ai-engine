## Current Bootstrap Scope

This change introduces a backend-only benchmark bootstrap using public datasets:

- IndoQA → Indonesian QA baseline
- EXAMS → educational reasoning coverage
- MIRAGE → technical RAG evaluation coverage

## Deferred Follow-up

The following are intentionally deferred:

1. Populated Kolabri-native benchmark dataset entries.
2. Public API benchmark execution surfaces.
3. Admin or ops benchmark management endpoints.

## Current Files Introduced

- `app/services/rag_benchmark_bootstrap.py`
- `data/benchmarks/public/*.json`
- `data/benchmarks/templates/kolabri_internal_placeholder.json`

## Placeholder Readiness

The internal placeholder exists only as a structural template for future Kolabri-native benchmark cases.
