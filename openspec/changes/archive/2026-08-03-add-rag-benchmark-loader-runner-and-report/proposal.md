## Why

Kolabri AI Engine now has a benchmark bootstrap contract and approved public dataset shortlist, but it still cannot execute a real benchmark flow end-to-end. This change is needed now so maintainers can actually load IndoQA, EXAMS, and MIRAGE, normalize them into the shared format, run a local backend-only benchmark, and produce a reviewable report.

## What Changes

- Introduce real dataset loaders for IndoQA, EXAMS, and MIRAGE.
- Introduce a unified backend-only benchmark runner that uses the shared normalized benchmark format.
- Introduce report output for local benchmark execution results.
- Keep execution local and internal only, without exposing a public benchmark surface.

## Capabilities

### New Capabilities
- `rag-benchmark-loaders`: Backend-only loaders for approved public benchmark datasets.
- `rag-benchmark-runner`: Unified local benchmark runner for normalized retrieval-quality evaluation.
- `rag-benchmark-reporting`: Local report output for benchmark execution and review.

### Modified Capabilities
- None.

## Impact

- Affected areas: benchmark loading utilities, normalization integration, local benchmark runner code, output/report generation, and backend-only evaluation workflows.
- Affected systems: public dataset ingestion into benchmark format, local retrieval-quality evaluation, and maintainer review artifacts.
- Explicitly out of scope: public API execution, admin/ops benchmark UI, remote orchestration, and fully populated Kolabri-native benchmark data.
