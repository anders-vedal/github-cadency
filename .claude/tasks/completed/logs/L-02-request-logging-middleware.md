# Task L-02: Request Logging Middleware

## Status
completed

## Blocked By
- L-01

## Blocks
- L-03, L-06

## Description
Add a FastAPI middleware that automatically injects `request_id`, `method`, and `path` into every log entry within a request lifecycle via structlog contextvars. Emits a `request.completed` log with status code and duration. Sets `X-Request-ID` response header for client correlation.

Based on the reference implementation at `.claude/docs/logging-export/source/middleware.py`.

## Deliverables

- [x] **backend/app/logging/middleware.py** — `LoggingContextMiddleware(BaseHTTPMiddleware)`:
  - On request entry: generate 8-char UUID prefix as `request_id`, clear contextvars, bind `request_id` + `method` + `path`
  - On completion: measure `duration_ms` via `time.monotonic()`, emit `request.completed` log with `status`, `duration_ms`, `event_type="system.http"`
  - Set `X-Request-ID` response header
  - Health check path filtering: skip logging for `GET /api/health` or similar noise endpoints
- [x] **backend/app/main.py** — Register middleware as **innermost** (after CORS, before route handlers):
  ```python
  app.add_middleware(LoggingContextMiddleware)
  ```
- [x] **backend/app/logging/__init__.py** — Export `LoggingContextMiddleware`

## Key Decisions
- **Innermost middleware**: Must be closest to route handlers so contextvars are available in all downstream code
- **8-char UUID prefix**: Short enough for log readability, unique enough for request correlation
- **Health check skip**: Avoid log spam from infrastructure probes (Promtail, Docker health checks)
- **No auth context binding**: Auth info (`user_id`, `app_role`) is not bound in middleware — it's available deeper in the request via dependency injection. Could add later if needed.

## Reference
- `.claude/docs/logging-export/source/middleware.py` — full middleware implementation
