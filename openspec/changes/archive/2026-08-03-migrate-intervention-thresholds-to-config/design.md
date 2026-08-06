## Context

`intervention.py` follows the same pre-extraction shape that `logic_listener.py` had before `ai-engine-quality-improvements`: thresholds are class constants and inline numeric literals scattered across decision paths. The refactor pattern is already proven by that change, so this slice replicates it for `intervention.py`.

## Goals / Non-Goals

**Goals:**
- All operational thresholds and the prompt-LLM temperature for `intervention.py` are sourced from `settings`.
- Class constants and inline numeric literals are removed.
- Behavior is unchanged when default settings are used.

**Non-Goals:**
- Tuning any value.
- Changing the intervention decision logic itself.
- Touching `LogicListener` (already migrated).

## Decisions

### D1: Settings names mirror the existing Logic Listener pattern
Use the prefix `INTERVENTION_` for parity with `LOGIC_LISTENER_*`. This makes `config.py` scannable.

### D2: Read once at construction, not per call
Same pattern as `LogicListener.__init__` — bind to `self.off_topic_threshold = settings.INTERVENTION_OFF_TOPIC_THRESHOLD` so tests can `monkeypatch` settings + reconstruct.

### D3: Confidence floors split per branch
Each numeric literal at `intervention.py:351–362` becomes its own setting. They are different decisions and should be tunable independently.

## Risks / Trade-offs

- **Risk: tests directly read class constants** → Mitigation: search for any reference to `OFF_TOPIC_THRESHOLD` outside `intervention.py` before removal.
- **Risk: more `config.py` entries dilute readability** → Mitigation: keep them in a `# Intervention Thresholds` section, mirroring the existing Logic Listener section.

## Open Questions

- None.
