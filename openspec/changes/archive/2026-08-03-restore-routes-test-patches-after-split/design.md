# Design

## Why Tests Broke

The original `routes.py` did:
```python
from app.services.monitoring import get_monitor
```
That bound the name `get_monitor` to the `app.api.routes` namespace. `mock.patch('app.api.routes.get_monitor', ...)` rebound that name. The route handler called `get_monitor()` resolving via module globals → got the mock.

After the split, `monitoring.py` has its own import:
```python
from app.services.monitoring import get_monitor
```
Now the name lives in `app.api.routes.monitoring`, not `app.api.routes`. Patches against the parent package raise `AttributeError: module 'app.api.routes' has no attribute 'get_monitor'`.

## Patch Path Mapping

Authoritative table for every patched factory:

| Old patch path | New patch path | Reason |
|---|---|---|
| `app.api.routes.get_document_processor` | `app.api.routes.documents.get_document_processor` | imported in `routes/documents.py` |
| `app.api.routes.get_efficiency_guard` | `app.api.routes.efficiency.get_efficiency_guard` | imported in `routes/efficiency.py` |
| `app.api.routes.get_engagement_analyzer` | `app.api.routes.analytics.get_engagement_analyzer` | imported in `routes/analytics.py` |
| `app.api.routes.get_export_service` | `app.api.routes.analytics.get_export_service` | imported in `routes/analytics.py` |
| `app.api.routes.get_intervention_service` | `app.api.routes.interventions.get_intervention_service` | imported in `routes/interventions.py` |
| `app.api.routes.get_llm_circuit_breaker` | `app.api.routes.health.get_llm_circuit_breaker` OR `app.api.routes.monitoring.get_llm_circuit_breaker` | depends on test's target endpoint |
| `app.api.routes.get_llm_service` | `app.api.routes.chat.get_llm_service` OR `app.api.routes.health.get_llm_service` | depends on endpoint |
| `app.api.routes.get_mongo_logger` | `app.api.routes.analytics.get_mongo_logger` OR `app.api.routes.health.get_mongo_logger` | depends on endpoint |
| `app.api.routes.get_monitor` | `app.api.routes.monitoring.get_monitor` | imported only in `routes/monitoring.py` |
| `app.api.routes.get_orchestrator` | one of `routes.{goals,groups,orchestration,analytics}` | depends on endpoint |
| `app.api.routes.get_rag_pipeline` | `app.api.routes.chat.get_rag_pipeline` | imported in `routes/chat.py` |
| `app.api.routes.get_reranker` | `app.api.routes.health.get_reranker` OR `app.api.routes.monitoring.get_reranker` | depends on endpoint |
| `app.api.routes.get_vector_store` | `app.api.routes.health.get_vector_store` OR `app.api.routes.documents.get_vector_store` | depends on endpoint |
| `app.api.routes.tempfile.NamedTemporaryFile` | `app.api.routes.documents.tempfile.NamedTemporaryFile` | only `documents.py` imports tempfile |

## Disambiguation Rule

When a factory is imported in multiple route submodules, the patch must target the **submodule that owns the endpoint under test**.

Example: `get_orchestrator` is imported by 4 modules. The test `test_group_dashboard_failure_returns_500` exercises `/api/groups/{id}/dashboard`, defined in `routes/groups.py`. Patch must be `app.api.routes.groups.get_orchestrator`.

To resolve each test, read its `client.get(...)/client.post(...)` URL and trace it to the route file, then patch in that module's namespace.

## Migration Approach

Single `tests/test_unit/test_routes_integration.py` file. Manual update per test (14 distinct symbols × ~6 endpoints average). Each test independently verifiable.

Order:
1. Group tests by endpoint URL prefix
2. For each group, resolve the owning route file
3. Update every `@patch('app.api.routes.<sym>')` to `@patch('app.api.routes.<owning_module>.<sym>')`
4. Run that test class, confirm green
5. Move to next group

## Risk: Patch-target drift in future splits

Out of scope for this change but noted: any future further split of route files (e.g. extracting `routes/groups.py` into `routes/groups/dashboard.py`) will require another patch-target audit. Mitigation: prefer dependency-injection in handlers (`Depends(get_monitor)`) over module-global lookups, which removes the need to patch by import path entirely. Tracked as follow-up scope.
