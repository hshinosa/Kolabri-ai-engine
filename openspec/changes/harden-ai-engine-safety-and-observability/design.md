## Context

Kolabri AI Engine already performs request validation, safety filtering, caching, and provider orchestration, but these concerns are distributed across multiple modules and do not yet form a consistently defined operational contract. The inspection also highlighted the need for clearer degraded behavior, stronger runtime hardening, and better observability around request handling, intervention flows, and model-provider failures.

## Goals / Non-Goals

**Goals:**
- Define a consistent runtime safety layer for request admission, safety-triggered handling, and model/provider failure isolation.
- Define observability requirements for health, tracing, metrics, and operator-facing diagnostics.
- Standardize degraded-mode behavior so upstream callers can distinguish transient, guarded, and terminal failures.
- Establish a verification baseline for safety and observability-sensitive paths.

**Non-Goals:**
- Replacing the entire provider abstraction layer.
- Re-architecting the whole RAG pipeline.
- Implementing product-facing UI dashboards in this change.

## Decisions

### 1. Separate runtime safety from observability as two capabilities
This keeps the spec boundary clear: one capability defines protective behavior, the other defines what the system must surface. The alternative was to merge both into one capability, but that would make later rollout and validation less precise.

### 2. Define degraded responses explicitly
Safety blocks, transient provider failures, and partial-service availability should not collapse into a single generic error path. The design will require differentiated behavior so callers and operators can reason about the system state. The alternative was to keep a generic 500-style response contract, but that would reduce operational clarity.

### 3. Require traceable diagnostics on critical AI-engine paths
Ingestion, retrieval, generation, intervention analysis, and safety decisions should expose structured diagnostics. The alternative was to rely on existing logs only, but inspection results suggest that current visibility is insufficient for future debugging and operational hardening.

### 4. Keep this change spec-first and implementation-agnostic
The change defines behavior and architecture expectations without binding the implementation to a specific tracing library or monitoring backend. This allows later implementation discussion without locking the team into a tooling choice prematurely.

## Risks / Trade-offs

- **More operational instrumentation may add overhead** → Mitigation: require instrumentation boundaries but leave sampling/verbosity configurable.
- **Degraded-mode contracts may require Core API alignment** → Mitigation: document upstream impact clearly and keep the response taxonomy explicit.
- **Stronger runtime safety could block borderline requests** → Mitigation: require auditability and operator-visible diagnostics for blocked flows.
- **Observability work can sprawl** → Mitigation: constrain the scope to AI-engine-critical paths only.

## Migration Plan

1. Define runtime safety behavior and observability requirements in specs.
2. Align implementation planning around logging, metrics, tracing, and degraded-mode response contracts.
3. Roll out changes behind configuration where possible to avoid abrupt production behavior shifts.
4. Validate operational behavior with targeted tests and deployment-stage verification.

## Open Questions

- Which tracing backend should be preferred during implementation?
- Which safety and degraded response fields must remain stable for Core API consumers?
- Which metrics are mandatory versus optional for initial rollout?

## Analysis (Pre-Implementation Discovery)

This section answers the discovery tasks defined in `tasks.md` (sections 1, 2, 3) and the Open Questions above. All findings are grounded in the current codebase snapshot of `Kolabri-ai-engine/`.

### A. Existing safety, guardrail, and error-classification surface (Task 1.1)

The runtime safety layer is currently distributed across these modules:

| Layer | Surface | Behavior today |
|---|---|---|
| HTTP edge | `app/middleware/auth.py` (`require_auth`) | API-key auth on every `/api/*` route via `app.include_router(..., dependencies=[Depends(require_auth)])` (`main.py:166`). |
| HTTP edge | `app/middleware/request_size_limit.py` | Hard cap 10 MB request bodies (`main.py:158`). |
| HTTP edge | `slowapi` Limiter on `main.py` | IP-keyed rate limit; rejection handled by `_rate_limit_exceeded_handler`. |
| Application | `app/core/guardrails.py` (`Guardrails.check_input` `:233`, `Guardrails.check_output` `:464`) | Returns `GuardrailResult(action ∈ {ALLOW, BLOCK, WARN, REDIRECT, SANITIZE})`; aggregates `InjectionDetector`, `ToxicityScorer`, `PIIDetector`, academic-honesty rules. |
| Application | `app/services/injection_detector.py`, `toxicity_scorer.py`, `pii_detector.py` | Standalone detectors that the Guardrails layer composes. |
| Provider | `app/services/circuit_breaker.py` + `app/core/circuit_breaker.py` | Wraps LLM calls with `CLOSED / OPEN / HALF_OPEN` state machine; recovery timeout from `settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT`. |
| Provider | `app/services/llm.py:20-25` | Hardcoded `RETRY_DELAY_BASE=1.0`, `RETRY_DELAY_MULTIPLIER=2.0`, `TIMEOUT_CONNECT=10.0`, `TIMEOUT_READ=90.0` used by retry/backoff. |
| HTTP error path | `main.py:170-220` | Three exception handlers — global `Exception` → `500 INTERNAL_SERVER_ERROR`, `StarletteHTTPException` (preserves `status_code`), and `RequestValidationError`. |
| HTTP error path | `app/api/routes.py` | 46+ inline `raise HTTPException(...)` calls. Consistent `400` for client validation, `500` for downstream failure. No distinct status for "guarded" or "degraded". |

Observed gaps:

1. **No distinct guarded outcome.** A Guardrails `BLOCK` decision is currently surfaced inside the response body of `/api/chat` (or equivalent) but is not distinguishable at the protocol level from a generic 500.
2. **Degraded vs terminal collapsed into 500.** Circuit-breaker `OPEN`, transient provider failures, and hard internal errors all flow through `global_exception_handler` and return the same shape.
3. **No request-correlation field.** Searching `app/` for `request_id` / `correlation_id` / `trace_id` returns zero matches — failures can be located by `path` + `method` + log timestamp only.

### B. Guarded / degraded / terminal outcome contract (Task 1.2)

Proposed runtime contract, backwards-compatible with the existing 500 path for unknown clients:

| Outcome | Trigger | HTTP status | Response shape |
|---|---|---|---|
| `guarded` | `Guardrails.check_input/check_output` returns `BLOCK` | `200` (chat-style) or `403` (other surfaces) | `{ "outcome": "guarded", "reason": "<rule_id>", "message": "<safe_message>", "request_id": "..." }` |
| `degraded` | Circuit breaker `OPEN`, provider transient failure, partial dependency outage detected by `/api/health` services map | `503` | `{ "outcome": "degraded", "reason": "<dependency>", "message": "<safe_message>", "retry_after": int, "request_id": "..." }` |
| `terminal` | Unhandled exception, validation collapse | `500` | `{ "outcome": "terminal", "detail": "INTERNAL_SERVER_ERROR", "request_id": "..." }` (extends today's shape, does not rename `detail`) |

The taxonomy is consumer-stable: existing clients reading `detail` continue to work; new clients reading `outcome` get the differentiation.

### C. Required runtime safety checkpoints (Task 1.3)

Mapped to the four critical AI-engine flows:

| Flow | Checkpoint | Today | After |
|---|---|---|---|
| Ingestion (`/api/documents/*`) | input validation, file-size limit, MIME check | size limit middleware + per-route validation | + structured emission of guarded outcome on rejection |
| Retrieval (`rag.py`) | grounding threshold, score floor | `_grounding_threshold` from `quality_controls`; literal in `rag.py:121` | + emit `guarded` outcome when grounding floor not met (instead of returning low-confidence answer silently) |
| Generation (`llm.py`) | retry, circuit breaker | retry constants in module (`llm.py:20-25`); circuit breaker around call | + emit `degraded` outcome when circuit `OPEN` or provider fails after retries |
| Intervention analysis (`logic_listener.py`, `intervention.py`) | threshold + cooldown | thresholds from `settings` (Logic Listener) and class constants (intervention) | + audit each intervention decision via the diagnostics path defined below |

### D. Observability boundaries (Task 2.1)

Telemetry is partially in place: `app/services/monitoring.py` exposes Prometheus `Counter` / `Histogram` / `Gauge` for request count, request latency, LLM call count/latency, RAG queries, cache hits/misses, errors, circuit-breaker state, and active connections. Structured logging is wired via `app/core/logging.py` using `structlog` with optional JSON renderer (`LOG_FORMAT="json"`).

Required boundaries to formalize:

| Boundary | Required signals |
|---|---|
| Ingestion | document size, modality, processing duration, success/failure outcome. |
| Retrieval | retrieval count, top-k, score distribution summary, grounding decision. |
| Generation | provider model, latency, retry count, circuit-breaker state at call time, outcome class. |
| Intervention | trigger type, threshold values used, decision (intervene / skip), suppression reason. |
| Safety | `Guardrails` rule that fired, action taken, `confidence`, `triggered_rules`. |

### E. Request-correlation and failure diagnostics (Task 2.2)

The implementation must add a `request_id` produced at the HTTP edge (middleware) and propagated through `structlog.contextvars` so that every downstream log line carries it without explicit threading. The same `request_id` MUST appear in:

1. The response body for `guarded`, `degraded`, and `terminal` outcomes (see § B).
2. Every log line emitted during the request via `structlog.contextvars.merge_contextvars` (already wired in `logging.py:30`).
3. Mongo activity logs for the request (`mongodb_logger.log_activity`).

This closes the gap surfaced in § A.3.

### F. Health and degraded-state reporting (Task 2.3)

The current `/api/health` endpoint (`app/api/routes.py:599-642`) reports a `services` map (`vector_store`, `llm`) and `reranker_enabled`, with overall status `"healthy"` or `"degraded"`. It should be extended with:

| Field | Meaning |
|---|---|
| `circuit_breaker.<name>` | per-circuit state (`closed` / `open` / `half_open`) |
| `dependencies.mongo` | reachable / degraded / down (currently not surfaced) |
| `dependencies.redis` | reachable / degraded / down (Redis cache exists in `app/core/redis_cache.py` but is not on the health map) |
| `last_request_id` | optional, for operator copy-paste correlation |

The endpoint must return `503` when overall state is `degraded` (it currently returns `200` with `status="degraded"`, which is silent for HTTP-level health probes).

### G. Validation scenarios (Task 3.1)

For each capability requirement, a verification scenario is defined:

| Capability requirement | Scenario | Verification surface |
|---|---|---|
| `runtime-safety: blocked-before-execution` | Submit a known-bad prompt to `/api/chat`; assert `outcome == "guarded"`, no provider call (verify via `monitoring.LLM_CALL_COUNT` delta = 0). | `tests/security/test_prompt_injection.py` already exercises this; extend to assert outcome shape. |
| `runtime-safety: degraded-on-dependency-failure` | Force circuit breaker `OPEN`; submit `/api/chat`; assert `503` + `outcome == "degraded"`. | Unit test under `tests/test_unit/test_circuit_breaker.py` extended with response-shape assertion. |
| `runtime-safety: terminal-stays-explicit` | Force unhandled exception; assert `500` + `outcome == "terminal"`. | Existing `test_api_routes.py` integration tests. |
| `safety: auditable-decisions` | Trigger `BLOCK`; assert structured log line with `rule_id`, `request_id`, `confidence`. | New unit assertion using `structlog.testing.capture_logs`. |
| `observability: critical-path-telemetry` | Submit a successful `/api/chat`; assert Prometheus counters increment for ingestion / retrieval / generation. | `tests/test_blackbox/test_api_blackbox.py` + `monitoring.get_metrics()`. |
| `observability: traceable-failure` | Submit a failing request; assert log lines for the request share the same `request_id`. | `structlog.testing.capture_logs` + assertion. |
| `observability: degraded-health` | Force vector_store down; assert `/api/health` returns `503` + `services.vector_store == False`. | Integration smoke. |

### H. Verification scope and boundary (Task 3.2, 3.3)

This change stays spec-first. It defines the contracts above; implementation slices for each capability are scoped to remain narrow:

| Slice | Scope | Verification |
|---|---|---|
| H1 | Add `request_id` middleware + structlog binding. | Log assertions only — no behavior change. |
| H2 | Extend `/api/health` to include circuit/Mongo/Redis state and switch overall `degraded` to `503`. | Health-check integration tests. |
| H3 | Introduce `outcome` field in error JSON for `Guardrails.BLOCK` decisions in chat-like routes. | Prompt-injection test extension. |
| H4 | Map circuit-breaker `OPEN` and provider-retry exhaustion to the `degraded` outcome shape. | Circuit-breaker unit tests + integration smoke. |
| H5 | Wire structured diagnostics for guardrail decisions through the existing `Guardrails` return value. | `structlog.testing.capture_logs` assertions. |

Each slice is independently verifiable.

### I. Answers to Open Questions

- **Tracing backend**: do not adopt an external tracer in this change. Use `structlog.contextvars` with a `request_id` field; if a tracer is added later, it can read the same context variable.
- **Stable response fields for Core API**: `outcome`, `reason`, `message`, `retry_after`, `request_id`. The legacy `detail` field is preserved as-is so existing Core API code paths do not break.
- **Mandatory metrics**: request count + latency, LLM call count + latency + outcome class, RAG retrieval outcome, circuit breaker state — these already exist in `monitoring.py`. Optional for initial rollout: per-rule guardrail counters and per-intervention-type counters.
