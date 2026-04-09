---
status: pending
priority: medium
depends_on: update-error-reporter.md (now completed)
---

# Wire remaining call sites with correct trigger_type

## Context

The ErrorReporter threshold gate has been removed and `trigger_type` support added.
Three scheduled call sites in `main.py` (AI analysis, notification eval, Linear sync) 
already have `trigger_type="scheduled"`. However, several gaps remain.

## Missing or incorrectly tagged call sites

### 1. `scheduled_sync()` in main.py (~line 124)
- The main GitHub sync wrapper does NOT call `_reporter.record()` on failure
- It delegates to `run_sync()` and only logs errors
- This is the core value prop of the app — sync failures must reach Sentinel
- Should use `trigger_type="scheduled"`

### 2. `slack.py:533` — Slack service error handler
- Calls `_reporter.record(exc, component=component)` without trigger_type
- Defaults to "request" but may be called from scheduled stale PR checks or 
  weekly digest (both scheduled jobs)
- Need to audit callers and pass appropriate trigger_type

### 3. `notifications.py:1306` — Notification service errors
- Calls `_reporter.record(exc=e, component=...)` without trigger_type
- Called from `evaluate_all_alerts()` which runs as a scheduled job
- Should use `trigger_type="scheduled"` when called from scheduled context

### 4. `integrations.py:208` — Background Linear sync 
- Calls `_reporter.record(e, component="services.linear_sync", endpoint_path=...)`
- This is a background task triggered by a user API call
- Should use `trigger_type="event"`

## Implementation notes

For slack.py and notifications.py, the cleanest approach may be to add a 
`trigger_type` parameter to the error-handling helper functions and pass it 
through from the caller context. This avoids hardcoding a trigger type that 
depends on who called the function.

## Acceptance criteria
- `scheduled_sync()` reports APP_BUG errors to Sentinel with `trigger_type="scheduled"`
- Slack scheduled jobs pass `trigger_type="scheduled"` through to reporter
- Notification evaluation passes `trigger_type="scheduled"`
- Background Linear sync uses `trigger_type="event"`
