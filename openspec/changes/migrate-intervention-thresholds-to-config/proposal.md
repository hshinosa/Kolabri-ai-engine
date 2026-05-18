## Why

`app/services/intervention.py` carries hardcoded operational thresholds (`OFF_TOPIC_THRESHOLD = 0.6` at line 55, `INACTIVITY_THRESHOLD_MINUTES = 30` at line 56, prompt LLM `temperature = 0.8` at line 243, and confidence floors `0.5/0.6/0.7/0.8` at lines 351–362). The `improve-ai-engine-testability-and-maintainability` change identified these as the first slice (§ G.S1) because the precedent is already set by `ai-engine-quality-improvements` for Logic Listener thresholds. Moving them to `config.py` is the smallest unit of work that improves operability and unblocks future tuning without code edits.

## What Changes

- Add new settings to `app/core/config.py`: `INTERVENTION_OFF_TOPIC_THRESHOLD`, `INTERVENTION_INACTIVITY_THRESHOLD_MINUTES`, `INTERVENTION_PROMPT_TEMPERATURE`, `INTERVENTION_CONFIDENCE_OFF_TOPIC`, `INTERVENTION_CONFIDENCE_INACTIVITY`, `INTERVENTION_CONFIDENCE_SUMMARIZE`, `INTERVENTION_CONFIDENCE_PROMPT`.
- Update `InterventionService.__init__` (or equivalent) to read each threshold from `settings.*` once at construction time.
- Remove the in-class constants and inline literals in `intervention.py`.
- Values do not change — refactor only.

## Capabilities

### Modified Capabilities

- `ai-engine-service-maintainability` — adds the requirement that intervention thresholds and prompt temperature live in `config.py`, not inline.

## Impact

- `app/core/config.py` — new settings.
- `app/services/intervention.py` — read from settings, remove inline constants.
- `tests/test_unit/test_*intervention*.py` (if any) — confirm thresholds still drive the same behavior.
