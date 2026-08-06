## 1. Pre-flight

- [x] 1.1 Run baseline: `cd /Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine && python -m pytest tests/ -x -q` — record test count (expect 357+). All must pass.
- [x] 1.2 Grep for `_legacy` imports: `grep -rn "_legacy" tests/ app/` — document all import sites that need updating.
- [x] 1.3 Verify `from app.api.routes import router` resolves and `len(router.routes)` is 39+.

## 2. Extract monitoring.py (no cross-dependencies)

- [x] 2.1 Create `app/api/routes/monitoring.py` with `router = APIRouter()`.
- [x] 2.2 Move endpoints: `GET /metrics` (L1233), `GET /health/monitoring` (L1251), `GET /health/circuit-breakers` (L1266), `GET /health/reranker` (~L1280+). Copy verbatim, adjust imports.
- [x] 2.3 Imports needed: `get_monitor`, `get_llm_circuit_breaker`, `get_reranker` from services; `Response`, `JSONResponse`, `HTTPException` from fastapi.
- [x] 2.4 `__init__.py`: add `from app.api.routes.monitoring import router as _monitoring_router` + `router.include_router(_monitoring_router)`.
- [x] 2.5 `python -m pytest tests/ -x -q` — must pass.

## 3. Extract conformance.py

- [x] 3.1 Create `app/api/routes/conformance.py` with `router = APIRouter()`.
- [x] 3.2 Move endpoints: `GET /conformance/check` (L1340), `POST /plan-vs-reality` (L1392). Copy verbatim, adjust imports.
- [x] 3.3 Imports needed: `get_orchestrator`, `get_mongo_logger`, schemas (`ConformanceCheckRequest`, `PlanVsRealityRequest`).
- [x] 3.4 `__init__.py`: add include.
- [x] 3.5 `python -m pytest tests/ -x -q` — must pass.

## 4. Extract goals.py

- [x] 4.1 Create `app/api/routes/goals.py` with `router = APIRouter()`.
- [x] 4.2 Move endpoints: `POST /goals/validate` (L773), `POST /goals/refine` (L823). Copy verbatim, adjust imports.
- [x] 4.3 Imports needed: `get_llm_service`, schemas.
- [x] 4.4 `__init__.py`: add include.
- [x] 4.5 `python -m pytest tests/ -x -q` — must pass.

## 5. Extract interventions.py

- [x] 5.1 Create `app/api/routes/interventions.py` with `router = APIRouter()`.
- [x] 5.2 Move endpoints: `POST /interventions` (L1456), `GET /interventions/{id}` (L1498). Copy verbatim, adjust imports.
- [x] 5.3 Imports needed: `get_intervention_service`, `InterventionType`, schemas.
- [x] 5.4 `__init__.py`: add include.
- [x] 5.5 `python -m pytest tests/ -x -q` — must pass.

## 6. Extract analytics.py

- [x] 6.1 Create `app/api/routes/analytics.py` with `router = APIRouter()`.
- [x] 6.2 Move endpoints: `POST /analytics/engagement` (L599), `GET /analytics/dashboard/group/{group_id}` (L639), `GET /analytics/dashboard/individual/{user_id}` (L660), `GET /analytics/export/group/{group_id}` (L681), `GET /analytics/export/group/{group_id}/csv` (L694), `GET /analytics/export/individual/{user_id}/csv` (L723).
- [x] 6.3 Imports needed: `get_engagement_analyzer`, `get_orchestrator`, `get_export_service`, `get_mongo_logger`, schemas.
- [x] 6.4 `__init__.py`: add include.
- [x] 6.5 `python -m pytest tests/ -x -q` — must pass.

## 7. Extract groups.py (largest module)

- [x] 7.1 Create `app/api/routes/groups.py` with `router = APIRouter()`.
- [x] 7.2 Move endpoints: `GET /groups/{group_id}/status` (L926), `POST /groups/{group_id}/track-participation` (L970), `POST /groups/{group_id}/start-monitoring` (L1012), `POST /groups/{group_id}/stop-monitoring` (L1048), `GET /groups/{group_id}/interventions` (L1089), `GET /groups/{group_id}/anomalies` (L1125), `GET /groups/{group_id}/recommendations` (L1154), `GET /groups/{group_id}/participation` (L1189).
- [x] 7.3 Imports needed: `get_orchestrator`, `get_logic_listener`, `get_intervention_service`, schemas, `Form`, `Query`.
- [x] 7.4 Verify LOC < 400.
- [x] 7.5 `__init__.py`: add include.
- [x] 7.6 `python -m pytest tests/ -x -q` — must pass.

## 8. Extract documents.py

- [x] 8.1 Create `app/api/routes/documents.py` with `router = APIRouter()`.
- [x] 8.2 Move endpoints: `POST /ingest` (L140), `POST /ingest/batch` (L194), `DELETE /documents/{id}` (L449).
- [x] 8.3 Move helper functions: `_process_ingest_background`, `_process_batch_file_background`, `ingest_document`, `ingest_batch` + all their imports.
- [x] 8.4 `__init__.py`: update re-exports to point to `documents.py` instead of `_legacy.py`.
- [x] 8.5 `python -m pytest tests/ -x -q` — must pass.

## 9. Extract chat.py

- [x] 9.1 Create `app/api/routes/chat.py` with `router = APIRouter()`.
- [x] 9.2 Move endpoints: `POST /ask` (L234), `POST /chat` (L278).
- [x] 9.3 Imports needed: `get_rag_pipeline`, `get_llm_service`, `get_guardrails`, `get_intervention_service`, `get_orchestrator`, `get_mongo_logger`, `PERSONAL_CHAT_STYLE`, schemas.
- [x] 9.4 `__init__.py`: add include.
- [x] 9.5 `python -m pytest tests/ -x -q` — must pass.

## 10. Delete _legacy.py + update __init__.py

- [x] 10.1 Verify all 33 endpoints are now in their new modules. Count: `grep -c "^@router\." app/api/routes/{documents,chat,analytics,goals,groups,monitoring,conformance,interventions}.py` should equal 33.
- [x] 10.2 Remove `_legacy_router` import and include from `__init__.py`.
- [x] 10.3 Delete `app/api/routes/_legacy.py`.
- [x] 10.4 `python -m pytest tests/ -x -q` — must pass.
- [x] 10.5 `python -c "from app.api.routes import router; print(len(router.routes))"` — should be 39+.

## 11. Update __init__.py final state

- [x] 11.1 `__init__.py` imports: 8 routers from per-capability modules + re-exports from `documents.py` (DI getters + ingest helpers).
- [x] 11.2 `__all__` list includes all re-exported names.
- [x] 11.3 No circular imports: `python -c "from app.api.routes import router"` works.

## 12. Verify

- [x] 12.1 `python -m pytest tests/ -x -q` — all 357+ tests pass.
- [x] 12.2 `python -m py_compile app/api/routes/*.py` — exit 0.
- [x] 12.3 `grep -rn "_legacy" app/ tests/` — zero matches (file deleted, imports updated).
- [x] 12.4 `openspec validate split-routes-remaining-capabilities --strict` — valid.
- [x] 12.5 Per-module LOC check: `wc -l app/api/routes/{documents,chat,analytics,goals,groups,monitoring,conformance,interventions}.py` — each < 400.
