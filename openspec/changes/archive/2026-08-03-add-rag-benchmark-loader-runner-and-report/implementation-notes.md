## Current Implementation Scope

This change implements:

- dataset-specific loaders for IndoQA, EXAMS, and MIRAGE sample benchmark inputs
- a unified backend-only local benchmark runner
- local JSON report output preserving dataset provenance and benchmark-role metadata

## Deferred Follow-up

The following are intentionally deferred:

1. Automatic remote fetching/downloading of benchmark datasets.
2. Public API benchmark execution.
3. Admin or ops benchmark UI/surfaces.
4. Full CI orchestration and leaderboard-style reporting.

## Current Output Shape

Local reports are written as JSON and include:

- summary of total cases and datasets
- per-dataset provenance and benchmark roles
- fallback counts
- per-case execution results
