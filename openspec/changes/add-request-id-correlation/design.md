## Context

`app/core/logging.py:30` already wires `structlog.contextvars.merge_contextvars` into the structlog pipeline, which means anything bound via `structlog.contextvars.bind_contextvars()` in middleware will automatically appear on every log line emitted during the request. This is the key seam — no change to `setup_logging()` is required.

The exception handler shape today (from `main.py:179-185`):

```json
{ "detail": "INTERNAL_SERVER_ERROR", "message": "An internal error occurred. Please try again later." }
```

The shape will be extended (not renamed) to:

```json
{ "detail": "INTERNAL_SERVER_ERROR", "message": "...", "request_id": "<uuid4>" }
```

`detail` is preserved so existing Core API consumers do not break.

## Goals / Non-Goals

**Goals:**
- Every inbound HTTP request gets a stable id from the moment middleware runs until the response finishes.
- Every log line emitted during the request carries the id automatically.
- 4xx and 5xx JSON responses surface the id so users can paste it back to operators.
- Mongo activity logs written during a request include the id.

**Non-Goals:**
- Distributed tracing (OpenTelemetry, W3C Trace Context, span propagation). Out of scope; left for a future change.
- Adding the id to every successful 2xx response body. The id is in the response **header** (`X-Request-ID`); only error bodies need to carry it inline so end users can copy it.
- Renaming or removing `detail` / `message` fields.

## Decisions

### D1: ASGI BaseHTTPMiddleware over starlette.middleware
Use `starlette.middleware.base.BaseHTTPMiddleware` so the middleware can read the incoming `X-Request-ID` header and bind contextvars before calling `await call_next(request)`. Lower-level pure ASGI middleware would also work but adds boilerplate without a behavioral benefit.

### D2: Reuse upstream `X-Request-ID` when valid
If the inbound request already carries `X-Request-ID` and it parses as a UUID, reuse it. Otherwise generate a fresh `uuid4()`. This lets Core API or load balancers carry an id forward without forcing them to.

### D3: Bind via `structlog.contextvars.bind_contextvars`
Already supported by the existing structlog pipeline. The binding lives for the duration of the coroutine, then we explicitly `unbind_contextvars` in a `finally` to avoid leakage in worker reuse.

### D4: Expose via `request.state.request_id`
The exception handlers in `main.py` receive `request: Request` — they can pull the id from `request.state.request_id`. If absent (e.g. middleware did not run because the failure happened earlier), fall back to a freshly generated id so the response body still carries one.

### D5: Mongo logger reads from contextvars, not function args
`MongoLogger.log_activity()` reads `structlog.contextvars.get_contextvars()` and merges any bound `request_id` into the document. Callers do not need to pass it explicitly. This matches the structlog pattern already used elsewhere.

## Risks / Trade-offs

- **Risk: middleware ordering** — must run before `LimitRequestSizeMiddleware` so that a request rejected for size still has an id. Mitigation: register first.
- **Risk: contextvar leakage across requests** — uvicorn/asyncio worker reuse could keep stale ids visible. Mitigation: `try/finally` with `unbind_contextvars` and use `bind_contextvars` per request, never module-level.
- **Risk: clients send malicious `X-Request-ID`** — only accept UUID-shaped values; ignore anything else and generate fresh.

## Open Questions

- None.
