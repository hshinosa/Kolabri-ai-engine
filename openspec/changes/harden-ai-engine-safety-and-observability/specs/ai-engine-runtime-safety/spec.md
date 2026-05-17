## ADDED Requirements

### Requirement: Runtime safety admission and guard handling
The AI engine MUST enforce a consistent runtime safety layer for inbound AI-facing requests before sensitive processing paths are executed.

#### Scenario: Unsafe request is blocked before execution
- **WHEN** an inbound request is classified as violating configured safety or guardrail rules
- **THEN** the system MUST stop the unsafe execution path before model or downstream processing continues

#### Scenario: Safety block returns an explicit guarded outcome
- **WHEN** a request is blocked by the runtime safety layer
- **THEN** the system MUST return a distinct guarded outcome that is distinguishable from a generic internal failure

### Requirement: Degraded-mode response taxonomy
The AI engine MUST distinguish safety-blocked, transient dependency failure, and terminal processing failure outcomes in its runtime contract.

#### Scenario: Dependency failure triggers degraded response
- **WHEN** a critical dependency such as a model provider or infrastructure service fails transiently during execution
- **THEN** the system MUST emit a degraded response classification rather than collapsing the outcome into an undifferentiated generic error

#### Scenario: Terminal failure remains explicit
- **WHEN** processing cannot continue and no degraded fallback is available
- **THEN** the system MUST return a terminal failure classification distinct from guarded and degraded outcomes

### Requirement: Safety decisions are auditable
The AI engine MUST capture structured diagnostics for runtime safety decisions that materially alter request execution.

#### Scenario: Safety-triggered decision emits diagnostics
- **WHEN** a request is blocked, downgraded, or rerouted by runtime safety logic
- **THEN** the system MUST record structured diagnostic context sufficient for later operator review
