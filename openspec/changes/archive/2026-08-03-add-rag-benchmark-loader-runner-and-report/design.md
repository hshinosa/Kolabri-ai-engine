## Context

The benchmark bootstrap change defined which public datasets should be used and what shape the internal benchmark contract should take, but it stopped short of an executable workflow. To make the benchmark useful in practice, the AI engine now needs a real local backend-only pipeline that can load approved datasets, normalize them into the shared shape, execute benchmark evaluation, and write reviewable output.

## Goals / Non-Goals

**Goals:**
- Define real loader behavior for IndoQA, EXAMS, and MIRAGE.
- Define a unified local backend-only benchmark runner that works across datasets through the normalized format.
- Define report output expectations for reviewable benchmark results.
- Preserve a strict internal-only boundary for benchmark execution.

**Non-Goals:**
- Public API endpoints for benchmark execution.
- Admin or operator management UI for benchmark runs.
- Automatic remote dataset download during every runtime request.
- Full CI orchestration or leaderboard publishing in this change.

## Decisions

### 1. Use one unified runner with dataset-specific loaders
Each dataset differs enough to justify its own loader, but the execution path should remain unified once cases are normalized. The alternative was dataset-specific runners, but that would duplicate execution and reporting logic.

### 2. Keep execution local and backend-only
The runner should be usable by maintainers locally without becoming part of a public runtime path. The alternative was exposing it through service endpoints, but that would expand scope and operational risk too early.

### 3. Report output is a first-class artifact
Running the benchmark without a durable reviewable output would reduce its practical value. The runner should therefore produce a structured local report that can be reviewed after execution. The alternative was terminal-only output, but that would make comparison and reuse harder.

### 4. Preserve normalization as the execution boundary
The loaders should convert raw dataset records into the shared benchmark format before the runner handles them. The alternative was letting the runner understand raw dataset-specific formats, but that would make the execution pipeline harder to maintain.

## Risks / Trade-offs

- **Dataset schema drift or format mismatch** → Mitigation: keep dataset-specific loaders isolated behind a normalized contract.
- **Runner scope can grow into a full benchmark platform** → Mitigation: restrict this change to local backend-only loading, execution, and reporting.
- **Reports may become too dataset-specific** → Mitigation: require a shared output structure with provenance and dataset-role fields.

## Migration Plan

1. Implement dataset-specific loaders that emit normalized benchmark cases.
2. Implement a unified local benchmark runner over the normalized format.
3. Implement report output for maintainers.
4. Validate that the runner stays backend-only and aligned with the benchmark bootstrap contract.

## Open Questions

- Should the runner initially operate on local prepared dataset files only, or also support optional download helpers later?
- What level of summary is required in the first report version: aggregate metrics only or aggregate + per-dataset section?
- How many sample cases per dataset should be expected for a lightweight first pass?
