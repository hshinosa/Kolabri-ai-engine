## Why

The first retrieval-quality iteration established internal controls, fallback behavior, and evaluation utilities, but it did not yet define a clear runtime contract for how backend components should consume those controls consistently. This change is needed now so the AI engine can use retrieval-quality controls internally in a predictable way without prematurely exposing them to public API callers or admin tooling.

## What Changes

- Define an internal-only runtime contract for retrieval quality controls used by backend service flows.
- Define how backend components resolve defaults, overrides, and bounded runtime plans for retrieval behavior.
- Define an internal evaluation workflow that backend maintainers can use to assess retrieval-quality changes before broader exposure.
- Explicitly defer any public API request overrides and admin/ops control surfaces.

## Capabilities

### New Capabilities
- `rag-internal-runtime-controls`: Internal backend-only runtime resolution of retrieval quality controls, fallback behavior, and bounded retrieval plans.
- `rag-internal-quality-evaluation`: Internal backend-only evaluation workflow and review criteria for retrieval-quality tuning.

### Modified Capabilities
- None.

## Impact

- Affected areas: `app/services/rag.py`, `app/services/vector_store.py`, `app/services/rag_quality.py`, config handling, and backend-only test/evaluation utilities.
- Affected systems: internal service orchestration for retrieval planning, reranking fallback, and quality review workflow.
- Explicitly out of scope: public request parameters, external API contract changes, admin endpoints, and operator-facing tuning surfaces.
