## Context

`split-routes-by-capability` converted `routes.py` to a package and established the aggregator pattern. `health.py` and `track_activity.py` are extracted. The remaining 33 endpoints in `_legacy.py` (1662 LOC) follow the same mechanical pattern: each tag group gets its own `APIRouter`, endpoints move verbatim, imports adjust.

The existing `__init__.py` already demonstrates the pattern:
```python
from app.api.routes._legacy import router as _legacy_router
router.include_router(_health_router)
router.include_router(_track_activity_router)
router.include_router(_legacy_router)
```

## Goals / Non-Goals

**Goals:**
- Extract 8 per-capability modules, each < 400 LOC.
- Existing integration tests pass without modification.
- `_legacy.py` deleted; `__init__.py` includes all 8 routers.
- Shared helper re-exports preserved (DI getters + ingest background tasks).

**Non-Goals:**
- Changing endpoint paths or schemas.
- Refactoring endpoint logic (pure mechanical move).
- Touching `app/api/batch_routes.py`.

## Decisions

### D1: Same pattern as health.py / track_activity.py
Each module gets its own `router = APIRouter()`. Endpoints move verbatim with only import adjustments.

### D2: Shared DI helpers stay re-exported from __init__.py
`__init__.py` re-exports `get_rag_pipeline`, `get_document_processor`, `get_vector_store`, `get_mongo_logger`, `get_logic_listener`, `get_llm_service`, `get_intervention_service`, `get_orchestrator`, `_process_ingest_background`, `_process_batch_file_background`, `ingest_document`, `ingest_batch`. These come from whichever module owns the function (documents.py for ingest helpers, etc.) and are re-exported.

### D3: Move modules in order of dependency independence
1. `monitoring.py` — no cross-dependencies
2. `conformance.py` — no cross-dependencies
3. `goals.py` — no cross-dependencies
4. `interventions.py` — no cross-dependencies
5. `analytics.py` — uses orchestrator, export_service
6. `groups.py` — uses orchestrator, logic_listener
7. `documents.py` — uses document_processor, vector_store (contains ingest helpers)
8. `chat.py` — uses rag, llm, guardrails, intervention, orchestrator (most complex)

### D4: ingest helpers → documents.py
`_process_ingest_background`, `_process_batch_file_background`, `ingest_document`, `ingest_batch` move to `documents.py`. Re-exported from `__init__.py` for backwards compatibility.

### D5: Delete _legacy.py after all extractions
No deprecation period. The file is internal, not public API. All tests pass → safe to delete.

## Risks / Trade-offs

- **Risk: import breakage** — Some test files may import directly from `_legacy.py`. Mitigation: grep for `_legacy` imports in tests and update to `__init__.py` re-exports.
- **Risk: circular imports** — chat.py imports many services. Mitigation: all imports are from `app.services.*` (one-directional dependency). No circularity expected.
- **Risk: line-count variance** — LOC estimates are approximate. If any module exceeds 400, split further (e.g. `groups.py` → `groups.py` + `groups_monitoring.py`).
