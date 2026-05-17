## ADDED Requirements

### Requirement: Retrieval quality controls remain backend-internal
The AI engine MUST keep retrieval quality controls available only to backend service and configuration boundaries for this iteration.

#### Scenario: Backend service resolves retrieval controls
- **WHEN** a backend service prepares a retrieval execution path
- **THEN** it MUST be able to resolve retrieval quality controls internally without requiring a public request-level override surface

#### Scenario: Public caller cannot directly tune runtime controls
- **WHEN** a public API caller interacts with the current AI-engine retrieval flow
- **THEN** retrieval quality controls MUST NOT be exposed as a new public tuning surface in this iteration

### Requirement: Runtime retrieval plans are resolved explicitly
The AI engine MUST resolve bounded retrieval plans internally before executing retrieval and optional reranking stages.

#### Scenario: Reranking is enabled internally
- **WHEN** reranking is enabled for a backend retrieval flow
- **THEN** the system MUST resolve an explicit plan for retrieval count, output count, and score threshold before execution

#### Scenario: Reranking is unavailable internally
- **WHEN** optional reranking is unavailable or fails during an internal backend flow
- **THEN** the runtime plan MUST fall back to a bounded vector-search path without widening the public contract
