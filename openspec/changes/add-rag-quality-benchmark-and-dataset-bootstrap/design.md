## Context

The AI engine can now evaluate retrieval quality internally, but there is still no practical benchmark package that maintainers can use immediately. Public datasets are the only realistic input source for the next step because there is not yet a curated Kolabri-native dataset. The benchmark bootstrap therefore needs to: (1) pick realistic public sources, (2) normalize them into a shared backend evaluation shape, and (3) keep a migration path open for future Kolabri-native benchmark cases.

## Goals / Non-Goals

**Goals:**
- Define a backend-only benchmark bootstrap based on approved public datasets.
- Assign a clear role to IndoQA, EXAMS, and MIRAGE within the benchmark workflow.
- Define a normalized benchmark case format that can support both public datasets now and Kolabri-native datasets later.
- Provide a placeholder template for future internal benchmark entries without requiring the dataset to exist today.

**Non-Goals:**
- Building a full public leaderboard or admin benchmark UI.
- Exposing benchmark execution through public API surfaces.
- Creating a fully populated Kolabri-native benchmark dataset in this change.
- Solving every multilingual or educational edge case in one bootstrap step.

## Decisions

### 1. Use a mixed public benchmark set instead of a single dataset
IndoQA, EXAMS, and MIRAGE serve different purposes and together provide a more practical starting point than any single source alone. The alternative was IndoQA-only, but that would under-cover reasoning and technical RAG evaluation.

### 2. Keep benchmark usage backend-only
The benchmark bootstrap should remain part of maintainer evaluation workflow, not a public runtime surface. The alternative was to wire benchmark controls into external APIs immediately, but that would expand scope prematurely.

### 3. Normalize all benchmark inputs to a shared internal format
Public datasets differ in schema and task shape. The bootstrap should define a common internal representation so evaluation code does not become dataset-specific. The alternative was one-off adapters without a shared contract, but that would not scale to future Kolabri datasets.

### 4. Include an explicit internal placeholder template
Even though no Kolabri-native benchmark dataset exists yet, the system should reserve a target shape for it now. The alternative was to defer that entirely, but doing so would make future migration less coherent.

## Risks / Trade-offs

- **Public datasets are not a perfect domain match** → Mitigation: use a mixed set with clearly assigned roles and keep a placeholder for future Kolabri-native data.
- **Normalization can hide source-specific nuances** → Mitigation: require provenance and dataset-role metadata in normalized entries.
- **Benchmark scope can sprawl into tooling/ops work** → Mitigation: keep this change limited to backend evaluation bootstrap and dataset contracts.

## Migration Plan

1. Define the benchmark bootstrap contract and approved public dataset roles.
2. Define the normalized dataset format for backend evaluation.
3. Define a placeholder template for future Kolabri-native benchmark data.
4. Implement benchmark loading and evaluation in later work using this contract.

## Open Questions

- How much of EXAMS should be used initially: full subject mix or a narrower educational subset?
- Should MIRAGE be consumed as-is or sampled down for a lightweight first benchmark pass?
- What metadata must be mandatory in the normalized format to preserve dataset provenance and benchmark role?
