## ADDED Requirements

### Requirement: Intervention thresholds and prompt temperature live in configuration

The AI engine MUST source intervention-service decision thresholds and prompt-LLM temperature from `app/core/config.py`, not from inline class constants or numeric literals in service code.

#### Scenario: Off-topic threshold is configurable

- **WHEN** the intervention service evaluates an off-topic decision
- **THEN** the service MUST use `settings.INTERVENTION_OFF_TOPIC_THRESHOLD` as the threshold

#### Scenario: Inactivity threshold is configurable

- **WHEN** the intervention service evaluates an inactivity decision
- **THEN** the service MUST use `settings.INTERVENTION_INACTIVITY_THRESHOLD_MINUTES` as the threshold

#### Scenario: Prompt-LLM temperature is configurable

- **WHEN** the intervention service constructs a prompt-generation LLM call
- **THEN** the call MUST use `settings.INTERVENTION_PROMPT_TEMPERATURE`

#### Scenario: Confidence floors are configurable per branch

- **WHEN** the intervention service emits a recommendation with a confidence value
- **THEN** that confidence MUST come from a named setting (`INTERVENTION_CONFIDENCE_*`) corresponding to the decision branch
