## MODIFIED Requirements

### Requirement: API surface is partitioned by capability

The AI engine MUST expose its HTTP API through per-capability modules under `app/api/routes/`, where each module owns the routes for one capability tag. `split-routes-by-capability` established the pattern with `health.py` and `track_activity.py`; this change implements the remaining 8 modules and deletes `_legacy.py`.

#### Scenario: Documents module owns ingest and delete endpoints

- **WHEN** `POST /api/ingest`, `POST /api/ingest/batch`, or `DELETE /api/documents/{id}` is called
- **THEN** the handler MUST be defined in `app/api/routes/documents.py`

#### Scenario: Chat module owns ask and chat endpoints

- **WHEN** `POST /api/ask` or `POST /api/chat` is called
- **THEN** the handler MUST be defined in `app/api/routes/chat.py`

#### Scenario: Analytics module owns engagement and dashboard endpoints

- **WHEN** `POST /api/analytics/engagement`, `GET /api/analytics/dashboard/group/{group_id}`, `GET /api/analytics/dashboard/individual/{user_id}`, or CSV export endpoints are called
- **THEN** the handler MUST be defined in `app/api/routes/analytics.py`

#### Scenario: Goals module owns validation and refinement endpoints

- **WHEN** `POST /api/goals/validate` or `POST /api/goals/refine` is called
- **THEN** the handler MUST be defined in `app/api/routes/goals.py`

#### Scenario: Groups module owns Logic Listener endpoints

- **WHEN** `GET /api/groups/{group_id}/status`, `POST /api/groups/{group_id}/track-participation`, start/stop monitoring, interventions, anomalies, recommendations, or participation endpoints are called
- **THEN** the handler MUST be defined in `app/api/routes/groups.py`

#### Scenario: Monitoring module owns metrics and health endpoints

- **WHEN** `GET /api/metrics`, `GET /api/health/monitoring`, `GET /api/health/circuit-breakers`, or `GET /api/health/reranker` is called
- **THEN** the handler MUST be defined in `app/api/routes/monitoring.py`

#### Scenario: Conformance module owns conformance and plan-vs-reality endpoints

- **WHEN** `GET /api/conformance/check` or `POST /api/plan-vs-reality` is called
- **THEN** the handler MUST be defined in `app/api/routes/conformance.py`

#### Scenario: Interventions module owns intervention endpoints

- **WHEN** `POST /api/interventions` or `GET /api/interventions/{id}` is called
- **THEN** the handler MUST be defined in `app/api/routes/interventions.py`

#### Scenario: _legacy.py is deleted

- **WHEN** all endpoints are extracted
- **THEN** `app/api/routes/_legacy.py` MUST NOT exist; the `__init__.py` aggregator includes all 8 routers directly

#### Scenario: No per-capability module exceeds 400 LOC

- **WHEN** any per-capability route module is reviewed
- **THEN** its line count MUST be under 400 LOC
