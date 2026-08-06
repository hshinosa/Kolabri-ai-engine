## Context

The previous RAG quality iteration introduced configurable retrieval thresholds, reranking integration, fallback behavior, and evaluation primitives. What is still missing is a narrow contract that says how these controls are meant to be used at runtime inside backend components only. Without this boundary, future implementation work could easily leak internal tuning controls into public request shapes or admin surfaces before the internal behavior stabilizes.

## Goals / Non-Goals

**Goals:**
- Define an internal-only runtime contract for retrieval quality controls.
- Define how backend services resolve default values and bounded override behavior internally.
- Define an internal retrieval-quality evaluation workflow for backend maintainers.
- Keep the runtime surface explicitly backend-only for this iteration.

**Non-Goals:**
- Exposing retrieval tuning via public API request parameters.
- Adding admin or ops endpoints for control inspection or mutation.
- Building a full benchmark platform or user-facing experimentation UI.

## Decisions

### 1. Keep runtime exposure internal to service/config boundaries
Retrieval controls should remain available only to backend code paths and internal configuration for now. The alternative was to expose them through API request contracts immediately, but that would widen scope and increase validation/security concerns before internal usage stabilizes.

### 2. Treat runtime plan resolution as a first-class backend concern
The system should explicitly resolve retrieval defaults, reranking expansion, thresholds, and output bounds before execution. The alternative was to continue scattering those decisions across the RAG path, but that makes backend behavior harder to review and evolve.

### 3. Keep evaluation workflow internal and maintainers-only
Quality evaluation should be available for backend decision-making without requiring external callers to understand or drive it. The alternative was to expose evaluation controls too early, but that would mix operational concerns with backend stabilization work.

### 4. Defer public surfaces intentionally
This change should make the internal runtime contract strong enough that later API or admin exposure can build on a stable backend core. The alternative was to partially expose controls now, but that would blur responsibility boundaries.

## Risks / Trade-offs

- **Internal-only scope may feel slower** → Mitigation: this creates a cleaner base for later API/admin exposure.
- **Backend runtime controls may still drift if not centralized enough** → Mitigation: define explicit runtime-plan ownership in specs and tasks.
- **Evaluation may remain underused without a command surface** → Mitigation: define review workflow now and allow later iteration to operationalize it.

## Migration Plan

1. Define internal runtime-control requirements for backend service usage.
2. Define internal evaluation workflow and review criteria for retrieval tuning.
3. Keep all exposure behind backend/service/config boundaries only.
4. Revisit public API/admin exposure in a later, separate change if needed.

## Open Questions

- Which backend service entry points should be the canonical consumers of runtime retrieval plans?
- Which internal overrides should be allowed in code paths beyond the main RAG query flow?
- What minimum evidence should maintainers require before promoting a retrieval tuning change broadly?
