# Fix Pre-existing Test Failures and Flaky Test Isolation

## Problem Statement

12 pre-existing test failures in `test_api_routes.py` due to stale mock paths after partial S3 route extraction. 3 flaky tests in `test_document_processor_full.py` due to PIL Image mock isolation when run with other test files.

## Proposed Solution

1. Update mock patch paths in `test_api_routes.py` to target correct submodules (`app.api.routes.health.*`, `app.api.routes.chat.*`, `app.api.routes.analytics.*`).
2. Add `_compute_similarity` sync mock alongside `_compute_similarity_async` in grounding verifier tests.
3. Fix `_patch_pil_image` autouse fixture to also patch `text_extraction.Image` and read from `sys.modules` at fixture time.

## Scope

- `tests/test_unit/test_api_routes.py` — 7 tests fixed
- `tests/test_unit/test_grounding_verifier_async.py` — 3 tests fixed
- `tests/test_unit/test_rag_accuracy.py` — 1 test fixed
- `tests/test_unit/test_coverage_gaps_extra.py` — 2 tests fixed
- `tests/test_unit/test_document_processor_full.py` — 3 flaky tests fixed

## Out of Scope

- Production code changes
- New test coverage
