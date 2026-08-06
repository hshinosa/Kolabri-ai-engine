## ADDED Requirements

### Requirement: Backend benchmark bootstrap uses approved public datasets
The AI engine MUST support a backend-only benchmark bootstrap based on approved public datasets while no Kolabri-native benchmark dataset exists.

#### Scenario: Maintainer prepares initial benchmark inputs
- **WHEN** a maintainer assembles the first benchmark workflow for retrieval-quality evaluation
- **THEN** the system MUST support approved public dataset sources without requiring a Kolabri-native dataset to exist first

### Requirement: Public dataset roles are explicit
The AI engine MUST define the intended evaluation role of each approved public benchmark dataset.

#### Scenario: Dataset shortlist is reviewed
- **WHEN** IndoQA, EXAMS, and MIRAGE are included in the benchmark bootstrap
- **THEN** the system MUST define why each dataset is included and what evaluation dimension it covers

### Requirement: Benchmark bootstrap remains backend-only
The AI engine MUST keep benchmark bootstrap usage within backend maintainer workflows during this iteration.

#### Scenario: Benchmark bootstrap is introduced
- **WHEN** public benchmark datasets are added to the evaluation workflow
- **THEN** they MUST NOT be exposed as a new public API execution surface in this iteration
