## Deferred Follow-up

This change intentionally keeps retrieval quality controls and review workflow internal to backend service/config boundaries.

Deferred to a later change:

1. Public API request-level overrides for retrieval controls.
2. Admin or ops endpoints for inspecting or mutating runtime retrieval tuning.
3. External operational workflow for runtime quality review beyond backend maintainer usage.

## Current Internal Runtime Consumers

- `app/services/rag.py`
- `app/services/vector_store.py`
- `app/services/rag_quality.py`

## Current Boundary Guardrail

- `app/api/schemas.py` continues to expose only the existing public request fields.
- Retrieval tuning remains driven by internal config/service logic only.
