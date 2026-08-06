## 1. Maintainability Baseline

- [x] 1.1 Identify the most change-prone and overgrown service workflows. — see `design.md` § A. Hotspots: `document_processor.py` (1,419 LOC), `app/api/routes.py` (1,712 LOC), `process_mining_anomaly.py` (770), `plan_vs_reality.py` (708), `rag.py` (615), `guardrails.py` (582), `logic_listener.py` (527, recently touched twice), `goal_validator.py`/`efficiency_guard.py`/`nlp_analytics.py` (480–510 each).
- [x] 1.2 Define maintainability boundaries for service decomposition and config ownership. — see `design.md` § B. Five named decomposition seams (document_processor by modality; routes.py by capability; rag.py retrieval-plan vs execution; logic_listener rule objects; plan_vs_reality / anomaly repository extraction).
- [x] 1.3 Map which operational defaults should move into explicit configuration control. — see `design.md` § C. Mapped table covering `intervention.py` thresholds (off_topic, inactivity, prompt temperature, confidence floors), `orchestration.py` risk-color thresholds, and `llm.py` retry/timeout constants. Logic Listener thresholds already migrated under `ai-engine-quality-improvements`.

## 2. Quality Gates

- [x] 2.1 Define unit-testability expectations for service-layer changes. — see `design.md` § D. Three rules: pure-logic exposed as standalone functions/rule objects; external boundaries reached via injectable seam; settings read at construction time.
- [x] 2.2 Define verification expectations for maintainability-focused refactors. — see `design.md` § E. Behavior preservation via affected unit + integration tests; clean LSP diagnostics on touched files; before/after responsibility note for hotspot modules.
- [x] 2.3 Define stronger quality gates for high-change or operationally sensitive service areas. — see `design.md` § F. Three gates: hotspot tag in proposal.md; targeted regression with reported counts; no silent threshold edits (must move to config or justify inline).

## 3. Follow-up Readiness

- [x] 3.1 Review the proposed capabilities against current test structure and service layout. — see `design.md` § A (last paragraph). Test ratio is skewed (88 unit / 6 integration) and Logic Listener tests already showed pre-existing event-loop flakiness on Python 3.13; the spec requirements in `ai-engine-service-maintainability` and `ai-engine-quality-gates` are consistent with this layout and do not assume more integration tests than currently exist.
- [x] 3.2 Ensure implementation follow-up can be staged incrementally without broad rewrite scope. — see `design.md` § G. Six independent slices (S1–S6), each shippable on its own and verifiable with existing test modules.
- [x] 3.3 Prepare implementation sequencing notes for later discussion. — see `design.md` § G + § H. Ordered priority: `intervention.py` config migration → `llm.py` retry/timeout config → `routes.py` capability split → `rag.py` retrieval-plan extraction → `document_processor.py` modality split → repository extraction in `plan_vs_reality.py` / `process_mining_anomaly.py`.
