## Context

The AI engine already has a RAG pipeline with ingestion, embedding, retrieval, and optional reranking, but inspection results showed that retrieval quality is constrained by default behavior, hidden thresholds, and limited explicit quality controls. There is also no strongly defined contract for evaluating retrieval quality improvements before making them part of the default experience.

## Goals / Non-Goals

**Goals:**
- Define configurable retrieval quality controls for retrieval and ranking behavior.
- Define how retrieval quality should be evaluated before tuning changes are adopted.
- Establish explicit fallback expectations when ranking or quality-enhancement stages are unavailable.
- Improve the spec-level contract for answer relevance without forcing a single implementation strategy.

**Non-Goals:**
- Replacing the vector database.
- Changing the product-level question-answering UX contract.
- Rewriting the full embedding pipeline in this change.

## Decisions

### 1. Treat retrieval controls and quality evaluation as separate capabilities
This separates runtime behavior from how the team decides whether changes are good enough. The alternative was a single capability, but that would mix operational controls with evaluation policy.

### 2. Make ranking and filtering behavior explicitly configurable
Thresholds, top-k behavior, and optional reranking should be defined as configurable quality controls. The alternative was to leave them as code-level defaults, but that limits operational tuning.

### 3. Require a defined fallback path when quality enhancers are unavailable
If reranking or optional ranking enhancements are unavailable, the RAG path should still behave predictably rather than failing ambiguously. The alternative was to let the path degrade implicitly, but that weakens reliability and quality interpretation.

### 4. Define evaluation requirements without locking in a single benchmark framework
The change should specify that quality must be measurable and comparable, but it should not over-constrain the future implementation. This keeps the design useful without prematurely choosing one evaluation stack.

## Risks / Trade-offs

- **More knobs can increase tuning complexity** → Mitigation: require explicit defaults and bounded configuration behavior.
- **Quality tuning may raise latency** → Mitigation: require fallback behavior and leave performance acceptance criteria visible during implementation.
- **Evaluation workflows can drift from production behavior** → Mitigation: require evaluation inputs to be traceable to real RAG use cases.

## Migration Plan

1. Define retrieval quality controls and evaluation requirements in specs.
2. Map current defaults to explicit configurable behavior.
3. Define rollout expectations for fallback handling and comparison testing.
4. Validate future implementation changes against the new quality requirements.

## Open Questions

- Which retrieval quality metrics will be mandatory for initial rollout?
- Should reranking be enabled by default immediately or staged behind configuration?
- What latency budget should constrain quality-enhancing stages?
