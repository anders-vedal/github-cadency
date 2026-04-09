# Update ErrorReporter for Sentinel Rule Engine

**Status:** Completed (2026-04-07)
**Priority:** Medium
**Depends on:** Sentinel migration 003 deployed (trigger_type + rule engine)

## Context

Sentinel's threshold engine has been upgraded from a single frequency-based threshold to a multi-rule system (burst, recurrence, spread). This enables detection of low-frequency recurring errors (e.g. nightly cron failures) that the old system silently dropped.

Two changes are needed in GitHub Cadency's error reporting:

1. **Remove the client-side frequency threshold** — report all `app_bug` errors to Sentinel
2. **Add `trigger_type` to error reports** — tell Sentinel whether the error came from an HTTP request, scheduled task, event consumer, or startup

## What to Change

### 1. Remove client-side threshold from ErrorReporter.flush()

The `ErrorReporter` currently only sends errors that cross a local frequency threshold (default: 5 occurrences in 1 hour). This gate must be removed. The buffer should still **deduplicate** by signature (so 100 identical errors in 5 min become 1 report with `frequency: 100`), but there should be no minimum frequency to send.

**Before:**
```python
def flush(self):
    now = time.time()
    reports = []
    for sig, entry in self._buffer.items():
        if now - entry.first_seen > self.threshold_window_seconds:
            continue  # expired
        if entry.frequency >= self.threshold_frequency:  # ← REMOVE THIS GATE
            reports.append(entry.to_report())
    self._buffer.clear()
    if reports:
        self._send(reports)
```

**After:**
```python
def flush(self):
    reports = [entry.to_report() for entry in self._buffer.values()]
    self._buffer.clear()
    if reports:
        self._send(reports)
```

### 2. Add `trigger_type` field to error reports

Add a `trigger_type` field to the report payload. Valid values:

| Value | When to Use | Example |
|---|---|---|
| `request` | HTTP request handler (default) | User hits `/api/metrics` |
| `scheduled` | Cron job, scheduled task | GitHub data ingestion, metric computation |
| `event` | Webhook handler | GitHub App webhook receiver |
| `startup` | App boot, lifespan startup | Migration runner, config validation |

**GitHub Cadency-specific guidance:**

- **GitHub App webhook handlers** → `"event"` (these process incoming webhooks from GitHub)
- **Scheduled ingestion/sync jobs** (e.g. periodic repo sync, metric recomputation) → `"scheduled"`
- **API request handlers** → `"request"` (default)
- **Startup/migration errors** → `"startup"`

**In the error report payload:**
```python
{
    "component": "jobs.github_sync",
    "error_code": "GitHubAPIError",
    "error_message": "...",
    "trigger_type": "scheduled",   # ← NEW FIELD
    "frequency": 1,
    ...
}
```

## Why This Matters

GitHub Cadency runs several scheduled jobs (repo sync, metric computation) that could fail silently under the old threshold system. With the new rule engine, Sentinel catches recurring failures via the **recurrence rule** (same error on 3+ distinct days) and applies stricter thresholds for scheduled tasks (2 distinct days instead of 3).

## Validation

After making these changes:
1. Deploy with the updated reporter
2. Confirm errors appear in Sentinel dashboard with the correct `trigger_type`
3. Verify heartbeat endpoint still receives pings
