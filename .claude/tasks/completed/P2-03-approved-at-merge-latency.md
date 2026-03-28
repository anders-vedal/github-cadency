# Task P2-03: Approved-At Timestamp and Post-Approval Merge Latency

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- 04-github-sync-service

## Blocks
None

## Description
Compute the timestamp of the last approval review and derive "time from approval to merge" — a critical phase where many PRs sit idle. Currently, `time_to_merge_s` lumps together review time and post-approval wait time. Separating these reveals whether delays are caused by slow reviews or slow merging after approval.

No new API calls needed — computable from existing `pr_reviews` data.

## Deliverables

### Database migration
Add columns to `pull_requests`:
- `approved_at` (DateTime, nullable) — timestamp of the last `APPROVED` review
- `time_to_approve_s` (Integer, nullable) — `approved_at - created_at` in seconds
- `time_after_approve_s` (Integer, nullable) — `merged_at - approved_at` in seconds (only for merged PRs)

### backend/app/services/github_sync.py (extend)
After syncing reviews for a PR, compute:
```python
approved_at = MAX(submitted_at) WHERE pr_id = this_pr AND state = 'APPROVED'
time_to_approve_s = (approved_at - pr.created_at).total_seconds() if approved_at else None
time_after_approve_s = (pr.merged_at - approved_at).total_seconds() if approved_at and pr.merged_at else None
```

### backend/app/services/stats.py (extend)
Add to `get_developer_stats()`:
- `avg_time_to_approve_hours` (float) — average time from PR creation to first/last approval
- `avg_time_after_approve_hours` (float) — average time from approval to merge

Add to `get_benchmarks()`:
- `time_to_approve_h` and `time_after_approve_h` as benchmarked metrics (lower is better)

### backend/app/schemas/schemas.py (extend)
- Add `avg_time_to_approve_hours: float | None` to `DeveloperStatsResponse`
- Add `avg_time_after_approve_hours: float | None` to `DeveloperStatsResponse`

## Merged-Without-Review Detection
Also add while touching this area:
- `merged_without_approval` (Boolean) on `PullRequest` — True if `is_merged = True` and no review has `state = 'APPROVED'`
- Count `prs_merged_without_approval` in `DeveloperStatsResponse`
- Add as a `WorkloadAlert` type: "N PRs merged without any approval this period"
