## Why

`split-routes-by-capability` (Complete) established the aggregator pattern and extracted `health.py` + `track_activity.py`. However `_legacy.py` remains at **1662 LOC with 35 route definitions** — it is still the single largest file in the repository and a merge hotspot. This change completes the capability split for the remaining 33 endpoints across 6 modules.

## What Changes

- Extract 6 per-capability modules from `app/api/routes/_legacy.py`:
  - `documents.py` — `POST /ingest`, `POST /ingest/batch`, `DELETE /documents/{id}` (~260 LOC)
  - `chat.py` — `POST /ask`, `POST /chat` (~170 LOC)
  - `analytics.py` — `POST /analytics/engagement`, dashboards, CSV exports (~230 LOC)
  - `goals.py` — `POST /goals/validate`, `POST /goals/refine` (~160 LOC)
  - `groups.py` — Logic Listener endpoints (8 routes: status, track-participation, start/stop monitoring, interventions, anomalies, recommendations, participation) (~360 LOC)
  - `monitoring.py` — `GET /metrics`, health endpoints (monitoring, circuit-breakers, reranker) (~200 LOC)
  - `conformance.py` — `GET /conformance/check`, `POST /plan-vs-reality` (~210 LOC)
  - `interventions.py` — `POST /interventions`, `GET /interventions/{id}` (~120 LOC)
- Delete `_legacy.py` after all endpoints extracted.
- Update `__init__.py` aggregator to include all 8 routers + re-export shared helpers.
- No endpoint URL or schema changes.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — completes the requirement that the API surface is partitioned by capability (one file < 400 LOC per capability).

## Impact

- `app/api/routes/_legacy.py` — deleted (all content migrated).
- `app/api/routes/{documents,chat,analytics,goals,groups,monitoring,conformance,interventions}.py` — new files.
- `app/api/routes/__init__.py` — updated to include all 8 routers + re-exports.
- `tests/` — import paths unchanged; all integration tests must pass without modification.
