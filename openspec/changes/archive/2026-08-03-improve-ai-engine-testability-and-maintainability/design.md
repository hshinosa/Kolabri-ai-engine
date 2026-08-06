## Context

Kolabri AI Engine has a strong feature set, but inspection results showed maintainability concerns in long service functions, hardcoded thresholds, and uneven test depth. These issues do not necessarily break runtime behavior today, but they increase the cost and risk of future changes. The design goal is to create a spec-level contract for cleaner decomposition, explicit configurability, and stronger verification expectations.

## Goals / Non-Goals

**Goals:**
- Define maintainability expectations for service decomposition and configuration ownership.
- Define quality-gate expectations for unit-testability and maintainability-sensitive verification.
- Reduce future change risk by making implicit implementation assumptions explicit at the spec level.

**Non-Goals:**
- Rewriting the entire AI-engine codebase in one pass.
- Mandating one exact module layout for every service.
- Replacing integration tests with unit tests.

## Decisions

### 1. Separate maintainability structure from quality gates
This allows the system to define what “clean enough to evolve” means separately from how changes are verified. The alternative was to merge both concepts, but that would blur architecture and verification responsibilities.

### 2. Prefer explicit configuration ownership over hidden code defaults
Operational decisions such as thresholds and feature toggles should be traceable to config boundaries whenever practical. The alternative was to leave them embedded in service logic, but that makes tuning and review harder.

### 3. Define testability in terms of decomposability and verifiable seams
The change should not prescribe every test implementation detail, but it should require service logic to be shaped in a way that makes unit-level verification realistic. The alternative was to define only test count goals, which would not solve the structural issue.

## Risks / Trade-offs

- **Refactoring for maintainability can expand scope** → Mitigation: keep this change focused on spec contracts, not broad rewrites.
- **More explicit quality gates may slow short-term delivery** → Mitigation: target the most change-prone service areas first during implementation planning.
- **Configurability can introduce complexity** → Mitigation: require ownership boundaries and documented defaults.

## Migration Plan

1. Define maintainability and quality-gate capabilities in OpenSpec.
2. Identify which service families and config boundaries are most affected.
3. Use the resulting tasks to stage implementation in narrow, verifiable slices later.

## Open Questions

- Which service families should be prioritized first during implementation?
- Which thresholds/config values should be mandatory to externalize?
- What is the minimum acceptable unit-testability standard for service modules?

## Analysis (Pre-Implementation Discovery)

This section answers the discovery tasks defined in `tasks.md` (sections 1, 2, 3) and the Open Questions above. All findings are grounded in the current codebase snapshot of `Kolabri-ai-engine/`.

### A. Change-prone and overgrown service workflows (Task 1.1, 3.1)

The AI engine has ~9,668 LOC across 24 files in `app/services/`. The top files by size and observed change frequency form the maintainability hotspots:

| File | LOC | Reason it is a hotspot |
|---|---|---|
| `app/services/document_processor.py` | 1,419 | Multiple ingestion concerns (PDF/DOCX/OCR/multimodal/chunking) collapsed into one module. |
| `app/api/routes.py` | 1,712 | Single router file aggregates all endpoints (chat, RAG, analytics, conformance, document, batch, track-activity). Already long enough to be split. |
| `app/services/process_mining_anomaly.py` | 770 | Conformance + anomaly detection + planning derivations entangled. |
| `app/services/plan_vs_reality.py` | 708 | Cross-cuts MongoDB log shape, session id resolution, and analytics math. |
| `app/services/rag.py` | 615 | Retrieval, scoring threshold logic, grounding orchestration in one class. |
| `app/services/logic_listener.py` | 527 | Recently touched twice (`ai-engine-quality-improvements`, `ai-engine-track-activity`); demonstrates high change frequency. |
| `app/core/guardrails.py` | 582 | Aggregates injection, toxicity, PII, academic-honesty rules; long `check_input`/`check_output` paths. |
| `app/services/goal_validator.py` / `efficiency_guard.py` / `nlp_analytics.py` | 482–505 each | Mixed analytics + LLM orchestration. |

Test coverage is uneven: there are **88 unit-test files** vs **6 integration-test files**, and the recent quality-improvements change observed *"66 passed, 8 pre-existing event loop failures di Python 3.13"* on `test_logic_listener*.py` alone — i.e. some flakiness is structural, not test-author error.

### B. Maintainability boundaries (Task 1.2)

Recommended decomposition seams (capability-aligned, not file-renaming):

1. **`document_processor.py`** → split by ingestion modality: text extraction, image/multimodal extraction, chunking, and storage adaptation. Each seam is independently unit-testable with file fixtures.
2. **`app/api/routes.py`** → split per capability: `routes/chat.py`, `routes/rag.py`, `routes/analytics.py`, `routes/document.py`, `routes/batch.py`, `routes/health.py`. The current `track-activity` and `health` endpoints are good first-cut candidates because they have minimal coupling.
3. **`rag.py`** → separate retrieval planning (scoring, threshold selection) from execution (vector store calls + grounding). The retrieval-planning seam is pure-function and trivially unit-testable.
4. **`logic_listener.py`** → already partially decomposed via the threshold-config change. Next seam: extract the silence/off-topic/participation rules into named rule objects so each can be unit-tested in isolation without touching the orchestrator.
5. **`process_mining_anomaly.py` + `plan_vs_reality.py`** → extract Mongo query shape into a thin repository layer; keep analytics math as pure functions.

### C. Operational defaults that must move to explicit config (Task 1.3)

Concrete hardcoded operational defaults still embedded in service code (sampled, not exhaustive):

| File | Constant | Current location | Proposed config key |
|---|---|---|---|
| `app/services/intervention.py:55` | `OFF_TOPIC_THRESHOLD = 0.6` | class constant | `INTERVENTION_OFF_TOPIC_THRESHOLD` |
| `app/services/intervention.py:56` | `INACTIVITY_THRESHOLD_MINUTES = 30` | class constant | `INTERVENTION_INACTIVITY_THRESHOLD_MINUTES` |
| `app/services/intervention.py:243` | `temperature=0.8` for prompt LLM | inline literal | `INTERVENTION_PROMPT_TEMPERATURE` |
| `app/services/intervention.py:351-362` | confidence floors `0.5/0.6/0.7/0.8` | inline literals | `INTERVENTION_CONFIDENCE_*` |
| `app/services/orchestration.py:332` | `g > 0.6 or q < 40` color thresholds | inline literals | `ORCHESTRATION_RISK_*_THRESHOLD` |
| `app/services/orchestration.py:344` | equity warning `> 0.6` | inline literal | shares `LOGIC_LISTENER_PARTICIPATION_INEQUITY_THRESHOLD` (already in config) |
| `app/services/llm.py:20-25` | `RETRY_DELAY_BASE=1.0`, `RETRY_DELAY_MULTIPLIER=2.0`, `TIMEOUT_CONNECT=10.0`, `TIMEOUT_READ=90.0` | module constants | `LLM_RETRY_*`, `LLM_TIMEOUT_*` |

The `ai-engine-quality-improvements` change has already established the precedent for moving Logic Listener thresholds into `app/core/config.py`. The same pattern applies here.

### D. Unit-testability expectations (Task 2.1)

Minimum acceptable standard for new or modified service-layer code:

1. **Pure logic** (scoring, threshold checks, classification, decomposition rules) MUST be exposed as standalone functions or rule objects callable without a running FastAPI app or external dependency.
2. **External boundary calls** (Mongo, Qdrant, LLM, embedding) MUST be reachable through an injectable seam (constructor arg, factory, or DI fixture) so unit tests can substitute them.
3. **Configuration-derived values** MUST be read from `settings` once at construction time, not re-read inside hot paths, so tests can override `settings` with `monkeypatch` and trigger re-construction.

### E. Verification expectations for maintainability refactors (Task 2.2)

A maintainability-sensitive change is verified when:

1. The targeted decomposition does not change observable behavior (verified by re-running the affected unit + integration tests, and `pytest -k <module>` for the touched seam).
2. Diagnostics on the changed files are clean (`lsp_diagnostics` per changed file).
3. For changes that touch a hotspot module from section A, an explicit "before/after LOC" or "before/after responsibility" note is captured in the change `tasks.md`.

### F. Stronger quality gates for high-change service areas (Task 2.3)

For the hotspots in section A, future changes additionally require:

1. **Hotspot tag**: the `proposal.md` MUST list which hotspot file(s) are affected.
2. **Targeted regression**: the change MUST run the corresponding unit-test module under `tests/test_unit/test_<service>.py` and report counts.
3. **No silent threshold edits**: changing any value in section C requires either (a) moving the constant to `config.py` first, or (b) explicitly noting in `tasks.md` that the value remains inline and why.

### G. Implementation staging (Task 3.2, 3.3)

The follow-up work can be staged in narrow slices without a broad rewrite:

| Slice | Scope | Verification |
|---|---|---|
| S1 | Move `intervention.py` thresholds to `config.py` (mirrors the recent Logic Listener pattern). | Unit tests for `intervention.py` + LSP. |
| S2 | Move `llm.py` retry/timeout constants to `config.py`. | Unit tests for `llm.py` + circuit-breaker tests. |
| S3 | Split `app/api/routes.py` by capability (start with `health` + `track-activity`, then `analytics`). | Integration smoke (`tests/test_integration/test_api_routes*.py`) + the existing verification script. |
| S4 | Extract retrieval planning seam from `rag.py`. | Unit tests for the new pure functions; existing RAG benchmark runner. |
| S5 | Decompose `document_processor.py` by modality. | Document-processor unit tests (multiple files already exist). |
| S6 | Repository extraction in `plan_vs_reality.py` / `process_mining_anomaly.py`. | Anomaly + planning unit tests. |

Each slice ships independently. None requires a global cutover.

### H. Answers to the Open Questions

- **Priority service families**: in order — `intervention.py` (smallest, fastest demo of the config pattern); `llm.py` (operationally sensitive); `routes.py` (split by capability); `rag.py` (retrieval planning); `document_processor.py` (largest, last).
- **Thresholds mandatory to externalize**: all entries in section C, plus any new threshold introduced by future changes (gate via section F.3).
- **Minimum unit-testability standard**: the three rules in section D; failure to meet them blocks acceptance for changes touching hotspot modules.
