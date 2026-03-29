# Task M-04: Call `compute_approval_metrics()` in Webhook Review Handler

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`handle_pull_request_review()` in `webhooks.py` calls `recompute_review_quality_tiers()` after upserting a review, but does NOT call `compute_approval_metrics()`. This means `approved_at`, `time_to_approve_s`, `time_after_approve_s`, and `merged_without_approval` remain stale until the next scheduled sync processes that PR.

For users relying on real-time webhook updates, approval-related metrics will be delayed by up to 15 minutes (incremental sync interval).

### Fix
Add a call to `compute_approval_metrics(db, pr)` after `recompute_review_quality_tiers()` in `handle_pull_request_review()`. Also add it to `handle_pull_request()` since merges arrive via the `pull_request` event.

### Files
- `backend/app/api/webhooks.py` — `handle_pull_request_review()` and `handle_pull_request()`

### Architecture Docs
- `docs/architecture/DATA-FLOWS.md` — Webhook Processing section
