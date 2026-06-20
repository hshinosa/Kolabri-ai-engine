## Why

The ai-engine test suite currently has 15 failing tests (out of 2452 total) that block CI and obscure new regressions. These failures fall into three distinct categories: environment/dependency issues with PaddleOCR under Python 3.13, stale test assertions that don't match updated production copy, and pre-existing logic bugs in grounding verification, RAG scaffolding, and async mocking. Fixing these failures now restores test suite health and enables reliable regression detection.

## What Changes

- **OCR Import Resilience**: Make OCR availability tests resilient to Python 3.13 + paddle 3.0.0 circular import issues by mocking paddle imports or skipping when paddle is broken, rather than importing the real broken module.
- **Socratic Hint Test Alignment**: Update test assertions in `test_intervention_and_goals.py::TestGenerateSocraticHint` to match current Indonesian hint copy in `goal_validator.py`.
- **Grounding Threshold Fix**: Correct `GroundingResult.is_grounded` logic so claims below threshold are marked `False`, not `True`.
- **RAG Scaffolding Passthrough**: Fix RAG query path to pass early/late scaffolding context through to results (currently returns `None`).
- **Week Metadata Filter Fix**: Correct Mongo week-metadata filter builder to produce expected `$and` structure (currently raises `KeyError: '$and'`).
- **Async Mock Correction**: Replace plain `MagicMock` with `AsyncMock` for async dependency in `test_orchestration_coverage.py::test_validate_goal_invalid_resets_streak`.

## Capabilities

### New Capabilities

- `ocr-import-resilience`: Ensures OCR import tests handle environment-specific import failures (Python 3.13 + paddle 3.0.0 circular import) by mocking or skipping rather than importing broken dependencies.
- `socratic-hint-test-alignment`: Aligns Socratic hint test assertions with current production Indonesian copy, covering all 5 SMART criteria (specific, measurable, time-bound, achievable, multiple-missing).
- `rag-grounding-and-correctness`: Fixes RAG and grounding logic bugs including grounding threshold evaluation, scaffolding context passthrough, week metadata filter structure, and async mock correctness.

### Modified Capabilities

<!-- No existing capabilities are being modified at the spec level -->
