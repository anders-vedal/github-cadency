# Phase 1: Bugfixes and Technical Debt

> Priority: High | Effort: Small | Impact: Medium
> Prerequisite: None
> Blocks: All other phases (clean foundation first)

## Status: Completed

## Bugs to Fix

### 1. Auto-mapped developers have empty `external_user_id`

**File:** `backend/app/services/linear_sync.py`, `auto_map_developers()` (~line 780)

**Problem:** When `auto_map_developers()` creates a `DeveloperIdentityMap` row via email match, it sets `external_user_id=""` (empty string). The comment says "Will be populated on next user list fetch" but no code path ever does this. Consequences:
- Auto-mapped users appear unmapped in the admin mapping UI (which matches on `external_user_id`)
- Queries filtering by `external_user_id` miss auto-mapped rows
- Admin must manually re-map every auto-mapped developer

**Fix:** During `auto_map_developers()`, also fetch the Linear users list (already available via `LinearClient`) and match by email to get the real `external_user_id`. Alternatively, the `list_linear_users()` function (called by `GET /integrations/{id}/users`) should write back `external_user_id` for auto-mapped rows that have empty strings.

**Preferred approach:** Enhance `auto_map_developers()` to accept the Linear users list (fetched once during sync) and store the correct `external_user_id` immediately. This avoids the extra API call per sync and fixes all auto-mappings going forward. Add a one-time backfill for existing empty-string mappings.

### 2. Route collision on `GET /integrations/issue-source`

**File:** `backend/app/api/integrations.py`

**Problem:** `GET /integrations/issue-source` is defined after `GET /integrations/{integration_id}/status` in the router. FastAPI may try to parse `"issue-source"` as an integer `integration_id`, fail with 422, and never reach the static route.

**Fix:** Move the `issue-source` endpoint definition BEFORE any `{integration_id}` parameterized routes in the router file. FastAPI matches routes in definition order within the same router.

**Verification:** Add an integration test that calls `GET /integrations/issue-source` and asserts 200 (not 422).

### 3. No concurrency guard on Linear sync

**File:** `backend/app/services/linear_sync.py`, `run_linear_sync()`

**Problem:** The scheduler and manual `POST /integrations/{id}/sync` can both trigger `run_linear_sync()` simultaneously. This can cause duplicate DB writes and race conditions. GitHub sync uses `pg_advisory_lock` to prevent this.

**Fix:** At the start of `run_linear_sync()`, check if there's already an active `SyncEvent` with `sync_type="linear"` and `status="started"`. If so, skip/return early. This matches the pattern used by the GitHub sync's concurrency check (409 Conflict from the API).

### 4. PR linking is a full table scan

**File:** `backend/app/services/linear_sync.py`, `link_prs_to_external_issues()` (~line 714)

**Problem:** Scans ALL PRs in batches of 500 on every sync. For 50k PRs that's 100 DB roundtrips per sync, even though only a handful of new PRs exist since last sync.

**Fix:** Add a `since` parameter to `link_prs_to_external_issues()`. Filter PRs by `PullRequest.updated_at >= since` (using the integration's `last_synced_at`). Fall back to full scan only when `since` is None (first sync).

### 5. `ExternalSprint.url` never populated

**File:** `backend/app/services/linear_sync.py`, `CYCLES_QUERY` and `sync_linear_cycles()`

**Problem:** The `ExternalSprint` model has a `url` column, the schema exposes it, but the GraphQL query doesn't request the URL field from Linear. The column is always NULL.

**Fix:** Either:
- (a) Add the URL field to `CYCLES_QUERY` and populate it during sync, OR
- (b) Construct the URL from Linear's standard pattern: `https://linear.app/{workspace}/cycle/{cycle_id}` using the workspace slug from `integration_config`

Option (b) is preferred — avoids an extra GraphQL field and is always derivable.

### 6. Scope data mixing points and counts

**File:** `backend/app/services/linear_sync.py`, `sync_linear_cycles()` 

**Problem:** `planned_scope` is set from `scopeHistory[0]` (Linear's point-based scope tracking), but `completed_scope` falls back to `total_issues - uncompleted` (issue count) when `completedScopeHistory` is empty. This means velocity charts can mix units.

**Fix:** Be consistent. When `scopeHistory` or `completedScopeHistory` arrays exist, use them (these are points). When they don't exist (old cycles or edge cases), use issue counts for BOTH planned and completed. Add a `scope_unit` field to `ExternalSprint` ("points" or "issues") so the frontend can label the Y-axis correctly.

Alternatively, document the behavior and always prefer the scope history arrays, with a clear fallback that uses the same unit for both planned and completed within a single sprint.

## Technical Debt

### 7. Sync interval not live-configurable

**File:** `backend/app/main.py` (scheduler setup), `backend/app/config.py`

**Problem:** GitHub sync has DB-backed `sync_schedule_config` + `PATCH /sync/schedule` for live reconfiguration. Linear sync reads `LINEAR_SYNC_INTERVAL_MINUTES` from env var at startup only.

**Fix (defer to Phase 6):** This is a larger change. For now, document the limitation. Full fix in `06-sync-robustness.md`.

### 8. Minor cleanup: triage duration guard

**File:** `backend/app/services/linear_sync.py` (~line 686)

**Problem:** `not in ("triage",)` is a single-element tuple test. Functionally correct but confusing.

**Fix:** Change to `!= "triage"` for clarity.

## Acceptance Criteria

- [ ] Auto-mapped developers have correct `external_user_id` populated
- [ ] Existing empty-string mappings are backfilled
- [ ] `GET /integrations/issue-source` returns 200 (not 422)
- [ ] Concurrent Linear sync attempts are prevented (second attempt returns early or 409)
- [ ] PR linking uses incremental `since` filter
- [ ] Sprint URLs are populated (constructed or fetched)
- [ ] Scope data uses consistent units within each sprint
- [ ] All existing tests pass
- [ ] New tests cover each fix

## Test Plan

- Unit test: `auto_map_developers()` stores correct `external_user_id`
- Integration test: `GET /integrations/issue-source` returns 200
- Integration test: concurrent sync trigger returns 409
- Unit test: `link_prs_to_external_issues()` with `since` parameter only processes recent PRs
- Unit test: scope unit consistency when `scopeHistory` is missing
