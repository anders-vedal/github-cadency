# Task P1-09: Sync Page UX — Multi-Step Sync Wizard, Resumability, Progress Visibility

## Phase
Phase 1 — Make It Usable

## Status
done

## Blocked By
None

## Blocks
None

## Description
The Sync Status page is a bare-minimum implementation: two buttons ("Full Sync" / "Incremental Sync") and a history table. Users have no control over what gets synced, no live feedback during sync, no way to recover from crashes, and no way to manage which repos are tracked — even though the backend already supports repo listing and tracking toggles.

### Core Problems
1. **No configurable scope** — user can't choose which repos to sync or how far back to go
2. **No crash resilience** — the entire sync is one giant uncommitted transaction; a crash mid-sync loses ALL progress across all repos
3. **No resume capability** — after a crash or rate-limit timeout, the only option is "start over from scratch"
4. **No live progress** — while a sync is running, the only feedback is a "started" badge; no per-repo progress
5. **No repo management UI** — backend supports toggling `is_tracked` per repo, but no frontend for it
6. **No scope explanation** — "Full Sync" vs "Incremental Sync" are unclear to users
7. **No error details** — the `errors` JSONB column exists but is never surfaced

### Root Cause: Architectural Gap
`run_sync()` today does a single `db.commit()` in its `finally` block after processing ALL repos. This means:
- `last_synced_at` per repo is never durably saved until the entire run finishes
- If the process crashes after syncing 45 of 50 repos, zero progress is persisted
- There's no per-repo status tracking on the `SyncEvent`
- There's no way to know which repos still need processing

## Architecture: Resumable Per-Repo Sync

### Key Design Decision: Commit Per Repo
The sync loop must commit after each repo completes. This is the single most important change — it makes everything else possible:
- Progress is durable (crash after repo 45 = 45 repos saved)
- `last_synced_at` is accurate per repo
- Live progress queries reflect real state
- Resume = "re-run with only the repos that haven't completed yet"

### Sync Job Model
Extend `SyncEvent` (or create a new `SyncJob` table — TBD during implementation) to track:

```
New fields on SyncEvent:
  - repo_ids: JSONB (list of int)    # Which repos to sync (null = all tracked)
  - since_override: datetime(tz)     # Custom "since" date (null = use default logic)
  - total_repos: int                 # Total count for progress bar
  - current_repo_name: str(512)      # Currently syncing (null when idle/done)
  - repos_completed_ids: JSONB       # List of repo IDs successfully synced
  - repos_failed_ids: JSONB          # List of repo IDs that errored
  - is_resumable: bool               # True if incomplete and can be resumed
  - resumed_from_id: int FK          # Points to the SyncEvent this resumed from
```

### Resume Flow
1. Sync starts with repos [A, B, C, D, E]
2. Crashes after completing [A, B, C] — `SyncEvent.status = "failed"`, `repos_completed_ids = [1, 2, 3]`, `is_resumable = True`
3. User clicks "Resume" → new `SyncEvent` created with `repo_ids = [4, 5]` (D and E only), `resumed_from_id` pointing to the failed event
4. Backend computes remaining repos as `repo_ids - repos_completed_ids` from the original event

### Concurrency Guard
Before starting any sync, check if there's already a `SyncEvent` with `status = "started"`. If so, reject with 409 Conflict. This prevents parallel syncs racing on upserts.

## Deliverables

### 1. Backend: Resumable Per-Repo Commit Architecture

#### 1a. Schema/Model changes
- [ ] Add new fields to `SyncEvent`: `repo_ids`, `since_override`, `total_repos`, `current_repo_name`, `repos_completed_ids`, `repos_failed_ids`, `is_resumable`, `resumed_from_id`
- [ ] Alembic migration for the new columns
- [ ] Update `SyncEventResponse` schema to include all new fields

#### 1b. Refactor `run_sync()` to commit per repo
- [ ] After each `sync_repo()` completes: append repo ID to `repos_completed_ids`, update counters, `db.commit()`
- [ ] Before each repo: set `current_repo_name`, `db.commit()` (so progress query shows current repo)
- [ ] On per-repo error: append to `repos_failed_ids` and `errors`, `db.commit()`, continue
- [ ] On completion: set `status = "completed"` (or `"partial"` if some repos failed), clear `current_repo_name`
- [ ] On crash/unhandled error: `is_resumable = True`, `status = "failed"`

#### 1c. Configurable sync trigger
- [ ] New schema `SyncTriggerRequest`:
  ```python
  class SyncTriggerRequest(BaseModel):
      sync_type: Literal["full", "incremental"]  # Controls "since" logic per repo
      repo_ids: list[int] | None = None           # None = all tracked repos
      since: datetime | None = None                # Override: ignore repo.last_synced_at, use this
  ```
- [ ] Refactor `POST /api/sync/full` and `POST /api/sync/incremental` → single `POST /api/sync/start` that accepts `SyncTriggerRequest`
- [ ] Keep old endpoints as thin wrappers for backward compat (scheduled jobs use them)

#### 1d. Resume endpoint
- [ ] `POST /api/sync/resume/{event_id}` — creates a new SyncEvent with `repo_ids` = (original `repo_ids` - `repos_completed_ids`), `resumed_from_id` = event_id
- [ ] Validate: original event must have `is_resumable = True` and `status != "started"`

#### 1e. Sync status endpoint
- [ ] `GET /api/sync/status` — returns the latest SyncEvent (with progress fields) + summary stats:
  ```json
  {
    "active_sync": { ...SyncEvent with progress fields... } | null,
    "tracked_repos_count": 42,
    "total_repos_count": 50,
    "last_successful_sync": "2024-01-15T10:30:00Z",
    "last_sync_duration_s": 1234
  }
  ```

#### 1f. Concurrency guard
- [ ] Before starting a sync, query for `SyncEvent.status == "started"` — if found, return 409 with message and the active event ID
- [ ] The frontend should show the active sync instead of allowing a new trigger

### 2. Frontend: Multi-Step Sync Wizard

Replace the two-button UI with a guided multi-step flow.

#### Step 1: Choose Scope
- [ ] Two main options presented as cards:
  - **Quick Sync** (incremental) — "Fetch changes since each repo's last sync. Fast, typically under 5 minutes."
  - **Custom Sync** — "Choose exactly what to sync and how far back."
- [ ] Quick Sync: one-click start (no further steps needed), uses all tracked repos + incremental logic
- [ ] Custom Sync: proceeds to Step 2

#### Step 2: Select Repositories (Custom Sync only)
- [ ] Show all repos from `GET /api/sync/repos` as a checklist
- [ ] Pre-select all tracked repos; untracked repos shown but unchecked and greyed
- [ ] "Select All Tracked" / "Deselect All" bulk actions
- [ ] Search/filter repos by name
- [ ] Show per-repo info: last synced (relative time), PR count, issue count
- [ ] Toggle tracking per repo via `PATCH /api/sync/repos/{id}/track` with optimistic update (changing tracking is a side action, not part of the sync config)

#### Step 3: Choose Time Range (Custom Sync only)
- [ ] Options:
  - **Since last sync** (default) — uses each repo's `last_synced_at` (same as incremental)
  - **Last N days** — dropdown: 7, 14, 30, 60, 90
  - **Custom date** — date picker for a specific "since" date
  - **All history** — no `since` filter; fetches everything (with warning: "This may take a very long time for repos with many PRs")
- [ ] Show estimated scope: "~X repos, ~Y PRs to process" (rough estimate from repo PR counts)
- [ ] Prominent note: "You can safely close this page. If the sync is interrupted, you can resume from where it left off."

#### Step 4: Confirm & Start
- [ ] Summary of selections: N repos, sync type, time range
- [ ] "Start Sync" button
- [ ] On start: transitions to the Active Sync view

### 3. Frontend: Active Sync Progress

When a sync is running (`GET /api/sync/status` returns an active sync):

- [ ] **Progress bar**: repos completed / total repos (e.g., "23 / 50 repos")
- [ ] **Current repo**: "Syncing: org/repo-name..."
- [ ] **Counters**: PRs synced, issues synced (updating live)
- [ ] **Elapsed time**: running timer
- [ ] **Per-repo error count**: if any repos failed, show count with expandable detail
- [ ] **Poll interval**: 3 seconds while active, 10 seconds when idle
- [ ] **Disable** the sync wizard while a sync is active (show the progress view instead)
- [ ] Pulsing/animated indicator for "in progress" state

### 4. Frontend: Resume & Error Handling

- [ ] When the most recent sync has `is_resumable = True`:
  - Show a prominent banner: "Previous sync was interrupted after X/Y repos. N repos remaining."
  - "Resume Sync" button (calls `POST /api/sync/resume/{id}`)
  - "Start Fresh" option (ignores the interrupted sync, starts a new one)
- [ ] Error detail panel on sync history:
  - If `errors` is non-empty: red badge with count, expandable to show per-repo errors
  - If `repos_failed_ids` is non-empty: list failed repos with error messages
  - Offer "Retry Failed" action (same as resume but only includes failed repos)

### 5. Sync History Improvements

- [ ] Show `total_repos` and `repos_synced` as "23/50" format
- [ ] Show `repos_failed_ids` count if > 0
- [ ] Relative timestamps ("2 hours ago") alongside absolute dates
- [ ] Highlight the currently-running sync row with pulsing indicator
- [ ] Show if a sync was a resume (link to original event)
- [ ] Expandable error detail per event

### 6. Sync Overview Panel (top of page, above wizard)

- [ ] Summary stats: total repos in org, tracked repos count, last successful sync timestamp, last sync duration
- [ ] Brief explanation text for sync types:
  - **Quick Sync:** "Fetches only changes since each repo's last sync. Runs automatically every {SYNC_INTERVAL_MINUTES} minutes."
  - **Custom Sync:** "Choose specific repos, time range, and scope."
- [ ] If a sync is active: show progress inline here instead of the wizard

### 7. Backend: Structured Error Handling & Retry

#### Current problems
- **Errors are flat strings** — `f"{repo.full_name}: {str(e)}"` loses error type, step, retryability, timestamp
- **No retry on transient failures** — a single 502/503/timeout from GitHub kills the entire repo sync; GitHub returns these regularly
- **Sub-repo errors silently swallowed** — check runs, tree sync, and deployments catch + `logger.warning()` but never appear in `sync_event.errors`; user has no idea these failed
- **`db.rollback()` nukes sibling progress** — if repo 30 fails, rollback loses repos 1-29 (fixed by per-repo commits, but the error model still needs structure)
- **Rate limit sleep is unbounded** — can sleep up to 1 hour; if Docker/systemd kills the process during sleep, no progress is saved

#### 7a. Structured error objects
- [ ] Replace flat error strings with structured JSONB objects:
  ```python
  # Each entry in sync_event.errors:
  {
    "repo": "org/repo-name",        # null for top-level errors
    "repo_id": 42,                  # null for top-level errors
    "step": "pull_requests",        # "pull_requests" | "reviews" | "review_comments" | "pr_files" | "check_runs" | "issues" | "issue_comments" | "repo_tree" | "deployments" | "init" | "unknown"
    "error_type": "github_api",     # "github_api" | "rate_limit" | "auth" | "timeout" | "database" | "unknown"
    "status_code": 502,             # HTTP status code if applicable, null otherwise
    "message": "502 Bad Gateway",   # Human-readable error message
    "retryable": true,              # Whether this error is transient and worth retrying
    "timestamp": "2024-01-15T10:32:15Z",
    "attempt": 2                    # Which retry attempt this was (1 = first try)
  }
  ```
- [ ] Helper function `make_sync_error(repo, step, exception) -> dict` that classifies the error type and retryability from the exception class

#### 7b. Error classification
- [ ] Classify errors by type and retryability:
  | Exception | `error_type` | `retryable` |
  |-----------|-------------|-------------|
  | `httpx.HTTPStatusError` 502/503/504 | `github_api` | `True` |
  | `httpx.HTTPStatusError` 401/403 | `auth` | `False` (token refresh needed) |
  | `httpx.HTTPStatusError` 404 | `github_api` | `False` |
  | `httpx.HTTPStatusError` 422 | `github_api` | `False` |
  | `httpx.TimeoutException` | `timeout` | `True` |
  | `httpx.ConnectError` | `timeout` | `True` |
  | `sqlalchemy.exc.DBAPIError` | `database` | `False` |
  | Rate limit exhausted | `rate_limit` | `True` (after wait) |
  | Other `Exception` | `unknown` | `False` |

#### 7c. Retry with exponential backoff for transient errors
- [ ] Wrap `github_get()` with retry logic for retryable HTTP errors:
  ```python
  MAX_RETRIES = 3
  RETRY_BACKOFF = [2, 8, 30]  # seconds — exponential-ish
  RETRYABLE_STATUS_CODES = {502, 503, 504}
  ```
- [ ] On retryable failure: log warning, sleep with backoff, retry up to `MAX_RETRIES`
- [ ] On final retry failure: raise the exception (caught by per-repo error handler)
- [ ] Also retry `httpx.TimeoutException` and `httpx.ConnectError`
- [ ] Do NOT retry 401/403/404/422 — these are not transient

#### 7d. Surface sub-repo errors
- [ ] Check runs, tree sync, and deployments currently swallow errors with `logger.warning()`. Instead:
  - Still continue on failure (don't fail the whole repo)
  - But append a structured error to `sync_event.errors` with the specific `step`
  - Set a flag on the repo entry (e.g., in `repos_completed_ids` metadata) indicating partial success
- [ ] Consider a per-repo status in the progress tracking:
  ```python
  # repos_completed_ids becomes a list of objects instead of plain IDs:
  {
    "repo_id": 42,
    "repo_name": "org/repo",
    "status": "ok" | "partial",     # "partial" = main sync ok but sub-steps failed
    "prs": 15,
    "issues": 8,
    "warnings": ["check_runs: 502 Bad Gateway", "repo_tree: truncated"]
  }
  ```

#### 7e. Rate limit improvements
- [ ] Before starting each repo, check if we're approaching the rate limit by reading cached headers from the last response. If remaining < 200, proactively sleep (instead of waiting until < 100 after a request)
- [ ] Log the rate limit state at the start of each repo: `"Starting repo org/name — rate limit: 4500/5000 remaining"`
- [ ] If a rate limit sleep exceeds 5 minutes, commit current progress before sleeping (in case the process is killed during the wait)
- [ ] Track total rate limit wait time on the sync event for visibility: new field `rate_limit_wait_s: int`

### 8. Backend: Structured Logging

#### Current problems
- Log lines are standalone — no sync event ID, no repo context
- No way to correlate log output with a specific sync run in the UI
- Warning-level logs for sub-repo failures (check runs, tree) that users never see
- No structured fields for log aggregation

#### 8a. Sync-scoped logger with context
- [ ] Create a contextual logger that automatically includes `sync_event_id` and `repo` in every log line during a sync:
  ```python
  # At the start of run_sync():
  sync_logger = logger.getChild(f"sync.{sync_event.id}")

  # Per-repo:
  repo_logger = sync_logger.getChild(repo.full_name)
  repo_logger.info("Starting repo sync", extra={"since": since, "sync_type": sync_type})
  repo_logger.info("Repo sync complete: %d PRs, %d issues", prs, issues)
  repo_logger.error("Repo sync failed at step %s: %s", step, error)
  ```
- [ ] Log format should include sync_event_id for grep-ability:
  ```
  2024-01-15 10:32:15 INFO  [sync.42.org/repo] Starting repo sync (since=2024-01-14T10:00:00Z, type=incremental)
  2024-01-15 10:32:18 INFO  [sync.42.org/repo] PRs: 15 fetched, 12 upserted
  2024-01-15 10:32:20 WARN  [sync.42.org/repo] check_runs failed (attempt 3/3): 502 Bad Gateway — continuing
  2024-01-15 10:32:20 INFO  [sync.42.org/repo] Repo complete (partial): 15 PRs, 8 issues, 1 warning
  2024-01-15 10:35:00 INFO  [sync.42] Sync complete: 50 repos (48 ok, 2 partial), 1234 PRs, 567 issues, 180s
  ```

#### 8b. Key log points (what to log and at what level)
- [ ] **INFO**: sync start/end, per-repo start/end with counts, rate limit proactive waits
- [ ] **WARNING**: sub-repo step failures (tree, check runs, deployments), retryable errors on retry, rate limit approaching
- [ ] **ERROR**: per-repo complete failure (after retries exhausted), sync-level failures, auth failures
- [ ] Do NOT log at ERROR for expected conditions (rate limit waits, 404 on optional resources)

#### 8c. Sync event log field
- [ ] Add `log_summary: JSONB` field on `SyncEvent` — a condensed version of the sync log stored in the DB:
  ```json
  [
    {"ts": "10:32:15", "level": "info", "msg": "Sync started: 50 tracked repos, type=incremental"},
    {"ts": "10:32:18", "repo": "org/repo-a", "level": "info", "msg": "Complete: 15 PRs, 8 issues"},
    {"ts": "10:33:05", "repo": "org/repo-b", "level": "warn", "msg": "check_runs: 502 after 3 retries"},
    {"ts": "10:35:00", "level": "info", "msg": "Sync complete: 48/50 repos, 2 partial, 180s"}
  ]
  ```
- [ ] This is NOT a full log — just milestones and errors. Cap at ~100 entries (drop oldest INFO entries if over limit, keep all warnings/errors)
- [ ] Surfaced in the frontend as an expandable "Sync Log" on the history detail view

### 9. Frontend: Error & Log Visibility

- [ ] **Sync history error column**: red badge with count if errors > 0, expandable to structured error list
- [ ] **Per-error detail**: show repo name, step that failed, error type, whether it was retried, HTTP status code
- [ ] **Retryable vs permanent**: visually distinguish retryable errors (amber, "will succeed on retry") from permanent errors (red, "needs investigation")
- [ ] **Sync log viewer**: expandable panel on sync detail showing the `log_summary` entries with color-coded levels (info=gray, warn=amber, error=red)
- [ ] **Active sync warnings**: during a running sync, if errors are accumulating, show a live warning count: "3 repos failed so far — sync continuing with remaining repos"
- [ ] **Rate limit indicator**: if the sync is currently sleeping for rate limits, show "Waiting for GitHub rate limit reset (~X minutes remaining)" instead of just "syncing..."

## Implementation Sequence

### Phase A: Backend resilience (do first — critical path)
1. Migration: add new `SyncEvent` columns (including `log_summary`, `rate_limit_wait_s`)
2. Structured error helper + error classification
3. Retry logic on `github_get()` with exponential backoff
4. Refactor `run_sync()` for per-repo commits + progress tracking
5. Structured logging with sync-scoped context
6. Surface sub-repo errors (check runs, tree, deployments)
7. Rate limit improvements (proactive check, pre-sleep commit)
8. Add concurrency guard
9. Add `POST /api/sync/start` with `SyncTriggerRequest`
10. Add `POST /api/sync/resume/{id}`
11. Add `GET /api/sync/status`
12. Test: verify crash recovery, resume, retry behavior, error structure

### Phase B: Frontend wizard + progress
1. Sync overview panel
2. Multi-step wizard (4 steps)
3. Active sync progress view (including rate limit indicator)
4. Resume banner + retry
5. Sync history improvements + error detail panel + log viewer
6. Repo management (tracking toggles integrated into Step 2)

## Files to Modify

### Backend
- `backend/app/models/models.py` — add new fields to `SyncEvent`
- `backend/app/schemas/schemas.py` — `SyncTriggerRequest`, update `SyncEventResponse`, new `SyncStatusResponse`
- `backend/app/services/github_sync.py` — major refactor: per-repo commits, configurable scope, concurrency guard
- `backend/app/api/sync.py` — new endpoints: `POST /sync/start`, `POST /sync/resume/{id}`, `GET /sync/status`
- New migration file

### Frontend
- `frontend/src/pages/SyncStatus.tsx` — complete rewrite: wizard, progress view, resume, history
- `frontend/src/hooks/useSync.ts` — new hooks: `useSyncStatus`, `useStartSync`, `useResumeSync`; update poll interval logic
- `frontend/src/utils/types.ts` — update `SyncEvent` type, add `SyncTriggerRequest`, `SyncStatusResponse`

## Files Created
- `backend/migrations/versions/015_add_sync_resumability.py` — Migration for new SyncEvent columns
- `frontend/src/pages/sync/SyncPage.tsx` — Main sync page orchestrator
- `frontend/src/pages/sync/SyncOverviewPanel.tsx` — Summary stats bar
- `frontend/src/pages/sync/SyncWizard.tsx` — 4-step wizard with useReducer
- `frontend/src/pages/sync/steps/StepChooseScope.tsx` — Quick vs Custom sync
- `frontend/src/pages/sync/steps/StepSelectRepos.tsx` — Repo checklist with search
- `frontend/src/pages/sync/steps/StepTimeRange.tsx` — Time range picker
- `frontend/src/pages/sync/steps/StepConfirm.tsx` — Summary + start
- `frontend/src/pages/sync/SyncProgressView.tsx` — Live progress during sync
- `frontend/src/pages/sync/ResumeBanner.tsx` — Resume interrupted sync
- `frontend/src/pages/sync/SyncHistoryTable.tsx` — Enhanced history with expandable rows
- `frontend/src/pages/sync/SyncErrorDetail.tsx` — Structured error display
- `frontend/src/pages/sync/SyncLogViewer.tsx` — Color-coded log entries
- `frontend/src/components/ui/checkbox.tsx` — shadcn checkbox component
- `frontend/src/components/ui/progress.tsx` — shadcn progress component

## Files Modified
- `backend/app/models/models.py` — SyncEvent: 10 new columns, errors type fixed to list
- `backend/app/schemas/schemas.py` — SyncTriggerRequest, SyncStatusResponse, enriched SyncEventResponse + RepoResponse
- `backend/app/services/github_sync.py` — SyncContext, per-repo commits, batch commits, retry, structured errors, logging, rate limits
- `backend/app/api/sync.py` — POST /sync/start, POST /sync/resume/{id}, GET /sync/status, enriched GET /sync/repos
- `backend/app/main.py` — scheduled_sync wrapper with concurrency check
- `backend/tests/integration/test_sync_api.py` — Updated for new endpoints + new test cases
- `frontend/src/utils/types.ts` — SyncEvent extended, new types added
- `frontend/src/hooks/useSync.ts` — useSyncStatus, useStartSync, useResumeSync hooks
- `frontend/src/App.tsx` — Route updated to SyncPage

## Deviations from Original Spec
- Old endpoints (`POST /sync/full`, `POST /sync/incremental`) removed entirely instead of kept as wrappers — simplifies codebase since scheduled jobs call `run_sync()` directly
- `repos_completed_ids` implemented as rich objects `[{repo_id, repo_name, status, prs, issues, warnings}]` instead of plain ID lists — provides better UX in the frontend
- Added `completed_with_errors` status (spec suggested `partial`) for syncs where some repos failed
- Check-runs fetch not paginated (pre-existing, noted for future fix)
- Concurrency guard uses application-level check (not DB-level advisory lock) — sufficient for single-process deployment

## Effort
Large (backend resilience is a significant refactor; frontend is a full page rewrite)
