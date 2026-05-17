## ADDED Requirements

### Requirement: Unified benchmark runner executes normalized cases
The AI engine MUST provide a unified local benchmark runner that operates on normalized benchmark cases regardless of source dataset.

#### Scenario: Multiple datasets are benchmarked locally
- **WHEN** normalized benchmark cases from different approved datasets are passed to the runner
- **THEN** the runner MUST execute them through a shared local backend-only evaluation path

### Requirement: Runner preserves dataset provenance
The AI engine MUST preserve source dataset and benchmark-role context through benchmark execution.

#### Scenario: Runner evaluates mixed-source cases
- **WHEN** the runner processes cases from multiple benchmark datasets
- **THEN** it MUST keep source dataset and benchmark-role metadata available for later reporting and review

### Requirement: Runner remains local/backend-only
The AI engine MUST keep benchmark execution local/backend-only in this iteration.

#### Scenario: Benchmark runner is introduced
- **WHEN** the benchmark runner is executed
- **THEN** it MUST NOT depend on a new public API execution path in this iteration
