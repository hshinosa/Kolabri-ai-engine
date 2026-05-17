## ADDED Requirements

### Requirement: Retrieval quality evaluation remains backend-internal
The AI engine MUST keep retrieval quality evaluation workflows and review criteria available to backend maintainers without exposing them as external runtime controls in this iteration.

#### Scenario: Maintainer evaluates retrieval tuning internally
- **WHEN** backend maintainers review a retrieval-quality change
- **THEN** they MUST be able to use an internal evaluation workflow and review criteria without relying on a public API control surface

### Requirement: Fallback-path evaluation is part of internal review
The AI engine MUST include fallback-path behavior in internal backend review of retrieval-quality changes.

#### Scenario: Quality change affects reranking path
- **WHEN** a retrieval-quality change alters ranking or reranking behavior
- **THEN** the internal review workflow MUST also assess the fallback retrieval path alongside the enhanced path

### Requirement: Internal review criteria remain bounded to backend use
The AI engine MUST define review criteria that support backend quality decisions without implying immediate external exposure of retrieval tuning.

#### Scenario: Review criteria are updated
- **WHEN** retrieval-quality review criteria evolve
- **THEN** they MUST remain scoped to backend/internal quality decisions until a separate change expands the exposure surface
