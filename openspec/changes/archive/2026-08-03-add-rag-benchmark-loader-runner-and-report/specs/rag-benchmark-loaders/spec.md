## ADDED Requirements

### Requirement: Approved public datasets have real backend loaders
The AI engine MUST provide real backend-only loaders for approved public benchmark datasets.

#### Scenario: Loader reads IndoQA benchmark input
- **WHEN** a maintainer prepares IndoQA benchmark data for local evaluation
- **THEN** the system MUST be able to load that data into the shared benchmark normalization path

#### Scenario: Loader reads EXAMS benchmark input
- **WHEN** a maintainer prepares EXAMS benchmark data for local evaluation
- **THEN** the system MUST be able to load that data into the shared benchmark normalization path

#### Scenario: Loader reads MIRAGE benchmark input
- **WHEN** a maintainer prepares MIRAGE benchmark data for local evaluation
- **THEN** the system MUST be able to load that data into the shared benchmark normalization path

### Requirement: Loader behavior remains backend-only
The AI engine MUST keep benchmark loader behavior internal to backend workflows in this iteration.

#### Scenario: Loader capability is introduced
- **WHEN** benchmark dataset loaders are added
- **THEN** they MUST NOT create a public runtime execution surface in this iteration
