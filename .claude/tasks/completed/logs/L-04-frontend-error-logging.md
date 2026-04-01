# Task L-04: Frontend Error Logging + Backend Ingestion

## Status
completed

## Blocked By
- L-01

## Blocks
- L-06

## Description
Add a lightweight structured logging utility to the frontend that captures errors and sends them to a backend ingestion endpoint. Backend logs these as `event_type="frontend.error"` through the same structlog pipeline, so all application logs (frontend + backend) end up in one place (Loki).

## Deliverables

### Backend

- [ ] **backend/app/api/logs.py** — New router with `POST /api/logs/ingest` endpoint:
  - Accepts batch of log entries: `[{level, message, event_type, context, timestamp, url, user_agent}]`
  - No auth required (frontend may not have a token during error scenarios)
  - Rate-limited: max 50 entries per request, max body 64KB
  - Logs each entry via structlog with `event_type="frontend.error"` (or `frontend.warn`), includes `source="frontend"` field
  - Returns 204 No Content
- [ ] **backend/app/schemas/schemas.py** — `FrontendLogEntry` and `FrontendLogBatch` Pydantic models
- [ ] **backend/app/main.py** — Register `logs` router

### Frontend

- [ ] **frontend/src/utils/logger.ts** — Structured logger utility:
  - `logger.error(message, context?)` / `logger.warn(message, context?)` / `logger.info(message, context?)`
  - Batches log entries in memory (flush every 5s or on 10 entries, whichever comes first)
  - Flush on `window.onbeforeunload` via `navigator.sendBeacon()`
  - Falls back to `console.error()` if beacon/fetch fails
  - Attaches: `timestamp` (ISO), `url` (current page), `user_agent`
  - Auto-captures unhandled errors via `window.onerror` and `window.onunhandledrejection`
- [ ] **frontend/src/components/ErrorBoundary.tsx** — Replace `console.error()` with `logger.error()`
- [ ] **frontend/src/utils/api.ts** — Log non-401 API errors via `logger.error()` with status, path, detail
- [ ] **frontend/src/main.tsx** — Initialize global error handlers (onerror, onunhandledrejection)

## Key Decisions
- **No auth on ingest endpoint**: Frontend errors can happen before/during auth. Rate limiting prevents abuse.
- **Batch + beacon**: Minimizes network overhead. `sendBeacon` ensures errors are captured even during page unload.
- **No `logger.debug()`**: Frontend debug logs are console-only, never sent to backend. Only warn/error are shipped.
- **Same Loki pipeline**: Frontend errors get `event_type="frontend.error"` label, queryable alongside backend logs in Grafana.
- **No source maps server-side**: Stack traces will be minified in prod. Source maps stay in the build — developers use browser devtools for detailed debugging. Loki captures the error message and context, which is sufficient for triage.

## API Contract

```
POST /api/logs/ingest
Content-Type: application/json

{
  "entries": [
    {
      "level": "error",
      "message": "Failed to fetch developer stats",
      "event_type": "frontend.error",
      "context": {"status": 500, "path": "/api/stats/developer/1"},
      "timestamp": "2026-03-31T12:00:00.123Z",
      "url": "http://localhost:3001/team/1",
      "user_agent": "Mozilla/5.0 ..."
    }
  ]
}

→ 204 No Content
```
