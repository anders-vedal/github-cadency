# Task M-05: Fix Collaboration Scores 30-Day Window

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`recompute_collaboration_scores()` is called at the end of `run_sync()` with `sync_event.since_override` as `date_from`. For full syncs, `since_override` is `None`, which causes `_default_range()` to default to last 30 days. This means the materialized `developer_collaboration_scores` table always reflects only the last 30 days regardless of how much historical data was synced.

### Problem
A full sync may fetch months of historical data, but collaboration scores are computed only for the last 30 days. The `works-with` feature and over-tagged detection only see recent interactions.

### Options
1. **Pass explicit date range** based on the oldest data actually synced
2. **Use the global date range** from the API request that triggered the query
3. **Compute for multiple periods** (e.g., 30d, 90d, all-time) and let the frontend select

Option 1 is simplest — pass `since_override or (now - 90 days)` to cover a wider default window.

### Files
- `backend/app/services/github_sync.py` — `run_sync()` call to `recompute_collaboration_scores()`
- `backend/app/services/enhanced_collaboration.py` — `recompute_collaboration_scores()` date handling

### Architecture Docs
- `docs/architecture/DATA-FLOWS.md` — Enhanced Collaboration section
