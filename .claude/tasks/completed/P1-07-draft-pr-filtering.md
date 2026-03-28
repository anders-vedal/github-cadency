# Task P1-07: Draft PR Filtering in Workload and Stats

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- 07-stats-service
- M4-workload-balance

## Blocks
None

## Description
`PullRequest.is_draft` is stored in the database (synced at `github_sync.py:203`) but never queried in any service function. Draft PRs are counted as regular open PRs in all workload calculations, inflating `prs_open`, `prs_waiting_for_review`, and the workload score. This creates misleading metrics.

## Deliverables

### backend/app/services/stats.py (extend)
- [x] Add `PullRequest.is_draft.isnot(True)` filter to all queries that count open PRs:
  - [x] `get_developer_stats()` — `prs_open` count
  - [x] `get_workload()` — `open_authored`, `prs_waiting_for_review`, stale PR detection
  - ~~`get_team_stats()` — aggregated open PR counts~~ (N/A: team stats counts PRs by date range, not open state)
- [x] Add new field `prs_draft` to developer stats: count of open draft PRs (separate from `prs_open`)
- [x] Stale PR alert excludes drafts (a draft open for 48h is not stale — it's in progress)

### backend/app/schemas/schemas.py (extend)
- [x] Add `prs_draft: int` to `DeveloperStatsResponse`
- [x] Add `drafts_open: int` to `DeveloperWorkload`

### backend/app/services/stats.py — workload score fix
- [x] Remove `reviews_given_this_period` from `total_load` — completed reviews are output, not load
- [x] New formula: `total_load = open_authored + open_reviewing + open_issues`

## Testing
- [x] Integration test: verify draft PRs are excluded from `prs_open` and workload counts
- [x] Integration test: verify `prs_draft` correctly counts only draft PRs
- [x] Integration test: verify workload score no longer inflated by high review output
- [x] Integration test: verify stale PR alerts exclude drafts but include regular stale PRs

## Deviations from Spec
- Used `isnot(True)` instead of `is_(False)` to safely handle `NULL` values in `is_draft` column
- `get_team_stats()` was not modified — it has no open PR count, only date-range-based totals
- `open_prs_reviewing` intentionally not filtered for drafts — reviewing a draft is still active work

## Files Modified
- `backend/app/schemas/schemas.py`
- `backend/app/services/stats.py`
- `frontend/src/utils/types.ts`
- `docs/API.md`

## Files Created
- `backend/tests/integration/test_draft_pr_filtering.py` (9 tests)
