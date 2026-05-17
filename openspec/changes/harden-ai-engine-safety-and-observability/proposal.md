## Why

The AI engine already includes safety and logging features, but the inspection found gaps in observability, operational hardening, and consistency around runtime protections. This change is needed now so the service can fail more safely, emit more actionable signals, and provide a stronger operational baseline before broader AI-engine improvements are implemented.

## What Changes

- Introduce a formal runtime safety and resilience capability for inbound requests, model calls, and degraded-service behavior.
- Introduce an observability capability for structured health signals, traceable request flow, and operational diagnostics.
- Standardize the contract for safety-triggered responses and degraded-mode responses.
- Define required monitoring and verification expectations for critical AI-engine paths.

## Capabilities

### New Capabilities
- `ai-engine-runtime-safety`: Runtime safeguards for request validation, safety enforcement, degraded handling, and failure isolation.
- `ai-engine-observability`: Structured telemetry, operational diagnostics, and traceable health signals for core AI-engine workflows.

### Modified Capabilities
- None.

## Impact

- Affected areas: `app/api/`, `app/middleware/`, `app/core/`, `app/services/`, logging/metrics helpers, and operational configuration.
- Affected systems: Core API to AI-engine integration, Redis-backed rate/caching behavior, model-provider execution path, and production diagnostics.
- Dependencies/systems impacted: structured logging, metrics emission, runtime guardrails, and deployment/runbook expectations.
