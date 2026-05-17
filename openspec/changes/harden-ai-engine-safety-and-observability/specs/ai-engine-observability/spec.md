## ADDED Requirements

### Requirement: Critical-path telemetry
The AI engine MUST emit structured telemetry for critical execution paths including ingestion, retrieval, generation, intervention analysis, and safety decisions.

#### Scenario: Request path emits structured signals
- **WHEN** a request traverses a critical AI-engine workflow
- **THEN** the system MUST emit structured telemetry that allows operators to identify the workflow stage and outcome

### Requirement: Traceable failure diagnostics
The AI engine MUST provide enough request-correlated diagnostics to support failure analysis across internal modules and external dependencies.

#### Scenario: Request failure can be correlated
- **WHEN** a critical workflow fails or degrades
- **THEN** the system MUST expose diagnostics that allow the failure to be correlated to the request path and affected dependency boundary

### Requirement: Observable operational health
The AI engine MUST expose health and operational signals that differentiate normal operation from degraded dependency states.

#### Scenario: Dependency degradation is visible operationally
- **WHEN** a required dependency is reachable but partially degraded or unhealthy
- **THEN** the system MUST expose health information that reflects degraded operation rather than reporting the service as fully healthy
