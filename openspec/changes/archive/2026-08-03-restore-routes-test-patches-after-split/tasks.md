## 1. Pre-flight

- [x] 1.1 Capture current failures: `pytest tests/test_unit/test_routes_integration.py -q 2>&1 | tail -5` (expect 82 fail)
- [x] 1.2 Confirm aggregator re-exports list in `app/api/routes/__init__.py` is unchanged (no new symbols added)
- [x] 1.3 Map every endpoint URL in the test file to its owning route submodule

## 2. Update patches: monitoring endpoints

- [x] 2.1 `/metrics` (`routes.monitoring`): `get_monitor` → `app.api.routes.monitoring.get_monitor`
- [x] 2.2 `/health/monitoring`: same
- [x] 2.3 `/health/circuit-breaker`: `get_llm_circuit_breaker` → `app.api.routes.monitoring.get_llm_circuit_breaker`
- [x] 2.4 `/health/reranker`: `get_reranker` → `app.api.routes.monitoring.get_reranker`

## 3. Update patches: chat endpoints

- [x] 3.1 `/api/ask` and friends: `get_rag_pipeline` → `app.api.routes.chat.get_rag_pipeline`
- [x] 3.2 chat-related `get_llm_service` → `app.api.routes.chat.get_llm_service`

## 4. Update patches: documents / ingest

- [x] 4.1 `/api/ingest` family: `get_document_processor` → `app.api.routes.documents.get_document_processor`
- [x] 4.2 ingest `get_vector_store` → `app.api.routes.documents.get_vector_store`
- [x] 4.3 `tempfile.NamedTemporaryFile` → `app.api.routes.documents.tempfile.NamedTemporaryFile`
- [x] 4.4 `delete_document` test → `app.api.routes.documents.get_vector_store`

## 5. Update patches: analytics / export

- [x] 5.1 analytics `get_engagement_analyzer` → `app.api.routes.analytics.get_engagement_analyzer`
- [x] 5.2 analytics `get_export_service` → `app.api.routes.analytics.get_export_service`
- [x] 5.3 analytics `get_mongo_logger` → `app.api.routes.analytics.get_mongo_logger`
- [x] 5.4 analytics `get_orchestrator` (when used in analytics endpoints) → `app.api.routes.analytics.get_orchestrator`

## 6. Update patches: groups / goals / orchestration / interventions / efficiency

- [x] 6.1 groups endpoints `get_orchestrator` → `app.api.routes.groups.get_orchestrator`
- [x] 6.2 goals endpoints `get_orchestrator` → `app.api.routes.goals.get_orchestrator`
- [x] 6.3 orchestration endpoints `get_orchestrator` → `app.api.routes.orchestration.get_orchestrator`
- [x] 6.4 intervention endpoints `get_intervention_service` → `app.api.routes.interventions.get_intervention_service`
- [x] 6.5 efficiency endpoints `get_efficiency_guard` → `app.api.routes.efficiency.get_efficiency_guard`

## 7. Update patches: health endpoint cluster

- [x] 7.1 `/api/health` related `get_llm_service` → `app.api.routes.health.get_llm_service`
- [x] 7.2 `/api/health` related `get_mongo_logger` → `app.api.routes.health.get_mongo_logger`
- [x] 7.3 `/api/health` related `get_vector_store` → `app.api.routes.health.get_vector_store`
- [x] 7.4 `/api/health` related `get_reranker` → `app.api.routes.health.get_reranker`
- [x] 7.5 `/api/health` related `get_llm_circuit_breaker` → `app.api.routes.health.get_llm_circuit_breaker`

## 8. Verify

- [x] 8.1 `pytest tests/test_unit/test_routes_integration.py -q` passes (0 fail)
- [x] 8.2 Full suite: `pytest tests/ --ignore=tests/benchmarks --ignore=benchmarks --no-cov -q` shows 0 failures (delta of -82 vs prior baseline)
- [x] 8.3 No new `@patch('app.api.routes.<factory>')` lines remain — only `settings`, `_process_*_background`, `ingest_*`
- [x] 8.4 `openspec validate restore-routes-test-patches-after-split --strict`
