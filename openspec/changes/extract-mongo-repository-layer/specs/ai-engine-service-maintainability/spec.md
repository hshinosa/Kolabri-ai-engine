## ADDED Requirements

### Requirement: Mongo activity-log queries live in a repository

The AI engine MUST funnel all `activity_logs` collection reads outside `MongoDBLogger` itself through a single repository module so analytics modules do not construct raw Mongo queries.

#### Scenario: Analytics modules call repository methods

- **WHEN** `plan_vs_reality.py`, `process_mining_anomaly.py`, or any other analytics module needs activity-log data
- **THEN** it MUST call methods on `ActivityLogRepository` instead of building Mongo `find` / `find_one` queries inline

#### Scenario: Repository is the single owner of query shape

- **WHEN** the activity-log query shape needs to change (e.g. an index hint or a new field projection)
- **THEN** the change MUST be made in `app/services/repositories/activity_log_repository.py` only

#### Scenario: Repository is mockable in tests

- **WHEN** a unit test exercises analytics math
- **THEN** it MUST be able to substitute the repository with a fake (or in-memory) implementation without a Motor dependency
