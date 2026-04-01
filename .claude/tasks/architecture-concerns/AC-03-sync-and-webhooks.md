# AC-03: Sync & Webhook Concerns

**Priority:** Planned
**Severity:** Medium
**Effort:** Medium
**Status:** Pending

## Finding #1: Sync Blocks APScheduler

- **File:** `backend/app/main.py:74-94`
- `scheduled_sync()` calls `await run_sync(...)` directly — this is a coroutine that can run for minutes/hours
- APScheduler's `AsyncIOScheduler` runs jobs in the event loop — a long-running sync blocks other scheduled jobs (Slack checks, notification evaluation) from firing on time
- Slack stale PR checks and weekly digests may be delayed by the sync duration

### Required Changes
1. Option A: Run `run_sync()` in a background task instead of awaiting it in the scheduler callback
2. Option B: Use APScheduler's `max_instances=1` with `asyncio.create_task()` to avoid blocking
3. Option C: Accept the delay — notification evaluation also runs post-sync, and Slack checks self-throttle with runtime hour checks

## Finding #2: Auto-Reactivation Overrides Manual Deactivation

- **File:** `backend/app/services/github_sync.py` (`resolve_author()`, `sync_org_contributors()`)
- When an admin manually deactivates a developer, the next sync can silently re-enable them if they appear in GitHub activity or org members
- Only a warning log is emitted — no admin notification, no reactivation-prevention mechanism
- This is by design (contributing devs should be tracked) but can surprise admins

### Required Changes
1. Option A: Add a `deactivated_by` column to `developers` — only auto-reactivate if `deactivated_by != "admin"`
2. Option B: Add a `prevent_auto_reactivation` boolean flag
3. Option C: Surface auto-reactivation events in the notification center (alert type `auto_reactivation`)
4. Recommendation: Option C is least invasive — adds visibility without changing sync behavior

## Finding #3: Webhook All-or-Nothing Commit

- **File:** `backend/app/api/webhooks.py:38-72`
- All webhook event handlers share a single `db.commit()` at the end
- If any handler fails (e.g., `handle_pull_request_review` raises), the entire webhook processing rolls back
- This means a valid issue event bundled with a failing PR event could both be lost

### Required Changes
1. This is acceptable for single-event webhooks (GitHub sends one event per webhook delivery)
2. The rollback on failure is correct — partial commits would leave inconsistent state
3. The concern is more about error propagation: on failure, GitHub retries the webhook, which is the correct behavior
4. No change needed — document as intentional

## Finding #4: Approval Metrics Stale After Review Webhook

- **File:** `backend/app/api/webhooks.py` (`handle_pull_request_review`)
- Calls `recompute_review_quality_tiers()` but NOT `compute_approval_metrics()`
- After a review webhook, `approved_at`, `time_to_approve_s`, `merged_without_approval` remain stale
- These fields only update on the next scheduled sync

### Required Changes
1. Add `await compute_approval_metrics(db, pr)` after `recompute_review_quality_tiers()` in `handle_pull_request_review()`
2. Import `compute_approval_metrics` from `github_sync`

## Finding #5: Issue Comment Parent Resolution via URL Splitting

- **File:** `backend/app/services/github_sync.py` (issue comment processing)
- Parent issue is resolved by splitting `issue_url` string: `split("/")[-1]`
- Assumes GitHub URL format `https://api.github.com/repos/{owner}/{repo}/issues/{number}`
- Fragile if GitHub ever changes the API URL format (unlikely but not guaranteed)

### Required Changes
1. Low risk — GitHub API URL format has been stable for 10+ years
2. Could add a regex with named groups for more robust parsing
3. No urgent change needed

## Finding #6: Webhook Dedup / Concurrency

- **File:** `backend/app/api/webhooks.py`
- No dedup mechanism — rapid events on the same PR (e.g., multiple review submissions) can trigger concurrent processing
- Each webhook re-fetches ALL reviews and comments for the PR, even if only one changed
- The upsert pattern makes this safe (idempotent) but wastes API rate limit budget

### Required Changes
1. Option A: Add a debounce/queue for webhook processing per PR
2. Option B: Accept the redundancy — upserts are idempotent and rate limit impact is minimal for webhooks
3. Recommendation: Option B — the current approach is correct, just not optimal
