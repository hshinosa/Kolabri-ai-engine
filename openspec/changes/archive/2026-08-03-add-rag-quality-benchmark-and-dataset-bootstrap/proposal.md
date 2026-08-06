## Why

Kolabri AI Engine now has internal retrieval controls and evaluation primitives, but it still lacks a concrete benchmark bootstrap that can be used immediately with public datasets. This change is needed now so retrieval-quality improvements can be evaluated consistently using realistic public data while internal Kolabri-specific datasets are still unavailable.

## What Changes

- Introduce a benchmark bootstrap capability for public retrieval-quality datasets used by the backend evaluation workflow.
- Define the initial public dataset shortlist and their roles: IndoQA, EXAMS, and MIRAGE.
- Define a normalized internal benchmark format that can ingest public datasets now and accept Kolabri-specific datasets later.
- Define a placeholder template for future internal Kolabri benchmark cases without requiring those cases to exist yet.

## Capabilities

### New Capabilities
- `rag-benchmark-bootstrap`: Backend-only benchmark bootstrap for evaluating retrieval quality using approved public datasets.
- `rag-benchmark-dataset-normalization`: Internal normalization contract for converting public benchmark sources and future Kolabri datasets into a shared evaluation format.
- `rag-benchmark-internal-template`: Placeholder template for future Kolabri-native benchmark cases.

### Modified Capabilities
- None.

## Impact

- Affected areas: backend-only evaluation utilities, benchmark data layout, retrieval-quality review workflow, and dataset ingestion/normalization helpers for evaluation.
- Affected systems: internal RAG benchmark workflow, quality review inputs, and benchmark documentation for maintainers.
- Explicitly out of scope: public API exposure, admin/ops tuning surfaces, and a fully populated internal Kolabri benchmark dataset.
