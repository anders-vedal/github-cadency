# Phase 6: Sync Robustness

> Priority: Medium | Effort: Medium | Impact: Medium
> Prerequisite: Phase 1 (bugfixes — concurrency guard is there, rest is here)
> Independent of: Phase 2-5, 7

## Status: Completed

## Problem

The Linear sync is significantly less robust than the GitHub sync. The GitHub sync has: cancellation support, resumability, granular progress tracking, rate limit handling with backoff, advisory lock for concurrency, structured log entries, and a DB-backed live-configurable schedule. The Linear sync has none of these.

For small workspaces this is fine. For larger teams with thousands of Linear issues, the sync can take minutes, during which there's no progress feedback, no way to cancel, and no protection against concurrent runs.

## Changes

### 6.1 Cancellation Support

**File:** `backend/app/services/linear_sync.py`, `run_linear_sync()`

Add `cancel_requested` checking at step boundaries and every 50-issue batch (same pattern as GitHub sync's `_check_cancel()`):

```python
async def _check_linear_cancel(db: AsyncSession, sync_event: SyncEvent) -> None:
    """Check if cancellation was requested. Raises SyncCancelled if so."""
    await db.refresh(sync_event, ["cancel_requested"])
    if sync_event.cancel_requested:
        sync_event.status = "cancelled"
        sync_event.is_resumable = True
        await db.commit()
        raise SyncCancelled("Linear sync cancelled by user")
```

Check at: before each step (projects, cycles, issues, linking, mapping) and every 50 issues within the issue sync loop.

**API:** The existing `POST /sync/cancel` endpoint sets `cancel_requested` on the active `SyncEvent`. It should work for Linear sync events too — verify it queries by `sync_type` or applies to any active sync.

### 6.2 Granular Progress Tracking

**File:** `backend/app/services/linear_sync.py`

Add progress fields to the Linear `SyncEvent`:

```python
sync_event.current_step = "syncing_issues"  # projects, cycles, issues, linking, mapping
sync_event.current_repo_issues_total = total_issues  # reuse existing field
sync_event.current_repo_issues_done = processed_count
await db.commit()  # commit every 50 items
```

Reuse the existing `SyncEvent` progress columns (`current_step`, `current_repo_prs_total/done`, `current_repo_issues_total/done`). The "repo" prefix is a misnomer for Linear but the columns work fine — the frontend can display them as "Issues: 150/300".

**Frontend:** The `SyncProgressView` already renders differently for `sync_type === "contributors"`. Add a `sync_type === "linear"` branch that shows step name + issue progress bar. Can reuse existing progress bar component.

### 6.3 Structured Log Entries

**File:** `backend/app/services/linear_sync.py`

Use the existing `log_summary` JSONB pattern (same as GitHub sync):

```python
_append_log(sync_event, "info", "Syncing Linear projects...")
_append_log(sync_event, "info", f"Found {count} projects")
_append_log(sync_event, "info", "Syncing Linear cycles...")
_append_log(sync_event, "info", f"Found {count} cycles across {team_count} teams")
_append_log(sync_event, "info", f"Syncing issues (incremental since {since})")
_append_log(sync_event, "info", f"Processed {count} issues")
_append_log(sync_event, "info", f"Linked {new_links} new PR-issue links")
_append_log(sync_event, "info", f"Auto-mapped {mapped} developers ({unmapped} unmapped)")
```

These entries power the sync log viewer on the Sync Detail page. Currently Linear sync events have no log entries, so the detail page shows empty.

### 6.4 Rate Limit Handling

**File:** `backend/app/services/linear_sync.py`, `LinearClient.query()`

Linear's API returns rate limit headers:
- `X-RateLimit-Remaining`: requests remaining
- `X-RateLimit-Reset`: unix timestamp when limit resets

Add handling in `LinearClient.query()`:

```python
async def query(self, query: str, variables: dict) -> dict:
    response = await self.client.post(...)
    
    # Rate limit handling
    remaining = int(response.headers.get("X-RateLimit-Remaining", 100))
    if remaining < 10:
        reset_at = int(response.headers.get("X-RateLimit-Reset", 0))
        wait_seconds = max(0, reset_at - time.time()) + 1
        logger.warning("Linear rate limit approaching", 
                       remaining=remaining, wait_seconds=wait_seconds,
                       event_type="system.linear_api")
        await asyncio.sleep(min(wait_seconds, 60))  # cap at 60s
    
    # Retry on 429
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 60))
        logger.warning("Linear rate limited", retry_after=retry_after,
                       event_type="system.linear_api")
        await asyncio.sleep(min(retry_after, 120))
        return await self.query(query, variables)  # single retry
    
    response.raise_for_status()
    # ... existing JSON parsing
```

### 6.5 Live-Configurable Sync Schedule

**Approach:** Extend the existing `sync_schedule_config` singleton or create a parallel `linear_sync_schedule_config` table.

**Recommended: extend existing config.** Add columns:
- `linear_sync_enabled` (bool, default True when integration active)
- `linear_sync_interval_minutes` (int, default 120)

**API:** Extend `GET/PATCH /sync/schedule` to include Linear schedule fields. Or add `GET/PATCH /integrations/{id}/schedule` for per-integration schedule config.

**Scheduler update:** When `PATCH` updates the interval, reschedule the APScheduler job live (same pattern as `PATCH /sync/schedule` does for GitHub sync in `main.py`).

### 6.6 Resumability (Stretch)

This is lower priority. The Linear sync is a single pass through projects → cycles → issues. If it fails mid-issues, the next run is incremental anyway (it uses `last_synced_at` for issue filtering). True resumability would mean tracking which pages were already processed within a single sync run.

**Recommendation:** Skip formal resumability for now. The incremental sync with `updatedAt` filter already handles the common case. Mark this as a future enhancement if real-world usage shows it's needed.

## Acceptance Criteria

- [ ] Linear sync can be cancelled via `POST /sync/cancel` with graceful shutdown
- [ ] Cancelled Linear syncs are resumable (next sync picks up incrementally)
- [ ] Progress tracking shows current step + issue count on sync detail page
- [ ] Log entries appear in sync detail log viewer
- [ ] Rate limit handling prevents 429 errors (proactive slowdown + retry)
- [ ] Sync interval is configurable at runtime via API (no restart needed)
- [ ] Frontend shows Linear sync progress (reuse existing progress components)
- [ ] All existing sync tests pass

## Test Plan

- Unit test: `_check_linear_cancel()` raises `SyncCancelled` when flag is set
- Unit test: rate limit handling sleeps when remaining < threshold
- Unit test: 429 response triggers retry with backoff
- Integration test: `POST /sync/cancel` stops an active Linear sync
- Integration test: `PATCH /sync/schedule` updates Linear sync interval
- Integration test: sync detail page shows log entries for Linear sync
