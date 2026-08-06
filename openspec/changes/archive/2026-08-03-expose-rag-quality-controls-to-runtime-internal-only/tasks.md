## 1. Internal Runtime Control Scope

- [x] 1.1 Identify the backend-only service and config boundaries that may consume retrieval quality controls.
- [x] 1.2 Define the canonical internal runtime-plan resolution path for retrieval count, output count, and thresholds.
- [x] 1.3 Define and verify bounded fallback behavior for internal reranking failures without exposing new public request controls.

## 2. Internal Evaluation Workflow

- [x] 2.1 Define the backend-maintainer workflow for internal retrieval-quality review.
- [x] 2.2 Define the minimum internal review criteria for evaluating retrieval tuning changes.
- [x] 2.3 Define how fallback-path quality must be included in internal review decisions.

## 3. Exposure Boundary Guardrails

- [x] 3.1 Confirm that runtime retrieval controls remain internal-only in this iteration.
- [x] 3.2 Confirm that no new public API request parameters are introduced by this change.
- [x] 3.3 Record the deferred follow-up for future API/admin exposure in a later change.
