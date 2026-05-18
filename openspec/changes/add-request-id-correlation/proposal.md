## Why

The harden-ai-engine-safety-and-observability change identified a gap: zero matches in `app/` for `request_id`, `correlation_id`, or `trace_id`. Failures can only be located by `path` + `method` + log timestamp, which makes correlating one user-facing failure to its log lines and downstream Mongo records hard. This is the prerequisite for the subsequent guarded/degraded outcome work because both H3 and H4 require a stable id to surface in the response body.

## What Changes

- Add HTTP middleware that produces a `request_id` per inbound request, accepts `X-Request-ID` from upstream when present, and echoes it in the response header.
- Bind that id into `structlog.contextvars` for the request's lifetime so every downstream log line carries it without explicit threading.
- Surface the id in the JSON body of the existing `global_exception_handler` and `http_exception_handler` so 5xx and 4xx responses are correlatable to logs.
- Extend `mongo_logger.log_activity` writes performed during a request to include the id when one is bound.

## Capabilities

### New Capabilities

<!-- None -->

### Modified Capabilities

- `ai-engine-observability` — adds the request-correlation requirement (per `harden-ai-engine-safety-and-observability` § E).

## Impact

- `app/middleware/request_id.py` — new file, ASGI middleware.
- `main.py` — register the middleware before `LimitRequestSizeMiddleware`; inject `request_id` into the JSON shape of `global_exception_handler` and `http_exception_handler`.
- `app/services/mongodb_logger.py` — when a `request_id` is bound in contextvars, attach it to every activity log document.
- `tests/test_unit/test_request_id_middleware.py` — new tests (header echo, structlog binding, exception-handler shape).
