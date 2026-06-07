# Restore Routes Test Patch Targets After Routes Split

## Problem Statement

Commit `c0550b1` (`split-routes-by-capability`) split `app/api/routes.py` into a routes package (`app/api/routes/{health,documents,chat,...}`). The new aggregator [app/api/routes/__init__.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/routes/__init__.py) only re-exports `router`, `settings`, and 4 background helpers. It does **not** re-export the 13 service factories that the original monolithic `routes.py` had imported at module level.

`tests/test_unit/test_routes_integration.py` was authored against the monolithic module and uses `@patch('app.api.routes.<symbol>')` for these 13 factories plus `tempfile`. After the split, those `AttributeError`s now produce **82 collection-time failures**:

| Patched symbol | Defined in | Used by route file |
|---|---|---|
| `get_document_processor` | `app.services.document_processor` | `routes.documents` |
| `get_efficiency_guard` | `app.services.efficiency_guard` | `routes.efficiency` |
| `get_engagement_analyzer` | `app.services.nlp_analytics` | `routes.analytics` |
| `get_export_service` | `app.services.export_service` | `routes.analytics` |
| `get_intervention_service` | `app.services.intervention` | `routes.interventions` |
| `get_llm_circuit_breaker` | `app.services.circuit_breaker` | `routes.health`, `routes.monitoring` |
| `get_llm_service` | `app.services.llm` | `routes.health`, `routes.chat` |
| `get_mongo_logger` | `app.services.mongodb_logger` | `routes.health`, `routes.analytics` |
| `get_monitor` | `app.services.monitoring` | `routes.monitoring` |
| `get_orchestrator` | `app.services.orchestration` | `routes.goals`, `routes.groups`, `routes.orchestration`, `routes.analytics` |
| `get_rag_pipeline` | `app.services.rag` | `routes.chat` |
| `get_reranker` | `app.services.reranker` | `routes.health`, `routes.monitoring` |
| `get_vector_store` | `app.services.vector_store` | `routes.health`, `routes.documents` |
| `tempfile` | stdlib | `routes.documents` |

These are pre-existing failures outside the scope of recent error-handling changes. The blocking effect:
- 82 tests fail at collect time, masking real regressions
- CI signal is degraded (a green build today does not prove monitoring/health/documents endpoints work)
- New contributors see a noisy red baseline and lose trust in the suite

## Proposed Solution

Update test patch targets to follow Python's "patch where the name is **looked up**" rule. Each factory is looked up in the route submodule that imports it, not in the package aggregator.

```python
# Before (broken after split)
@patch('app.api.routes.get_monitor')
def test_metrics_failure(mock_monitor):
    ...

# After (canonical, matches actual import binding)
@patch('app.api.routes.monitoring.get_monitor')
def test_metrics_failure(mock_monitor):
    ...
```

This:
- Aligns tests with the new package structure
- Keeps the aggregator [app/api/routes/__init__.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/app/api/routes/__init__.py) clean per the completed `cleanup-routes-init-aggregator` change (no name-soup re-exports)
- Restores 82 tests to passing without touching production code

## Why Patch Submodules (Not Re-export from `__init__`)

Adding 13 re-exports to the aggregator would:
- Re-introduce the very name-soup that `cleanup-routes-init-aggregator` removed
- Create two import paths for every factory (confusing)
- Tempt code readers to import from the aggregator, defeating the split

`patch where used` is the documented Python pattern (`unittest.mock` docs). The test code is the part out of date, not the production layout.

## Scope

- Update all `@patch('app.api.routes.<symbol>')` decorators in [tests/test_unit/test_routes_integration.py](file:///Users/hshino/Kuliah/ProjectTA/Kolabri-ai-engine/tests/test_unit/test_routes_integration.py) to target the correct submodule
- 13 factory patches + 1 `tempfile` patch
- Keep `app.api.routes.settings` and `app.api.routes._process_*_background` patches as-is (those names *are* re-exported intentionally)

## Out of Scope

- Adding factory re-exports to the aggregator
- Refactoring `test_routes_integration.py` beyond the patch path update
- Changing route handler structure
