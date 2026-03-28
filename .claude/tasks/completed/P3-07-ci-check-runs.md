# Task P3-07: CI/CD Check-Run Integration

## Phase
Phase 3 — Make It Proactive

## Status
completed

## Blocked By
- 04-github-sync-service

## Blocks
- P4-01-dora-metrics

## Description
Track GitHub Actions check runs per PR to surface CI/CD quality signals: PRs merged with failing checks, flaky test detection (multiple retries before green), build duration trends. This is the largest single architectural gap for QA use cases.

## Deliverables

### Database migration
- [x] Add `head_sha` (String(40), nullable) to `pull_requests`
- [x] New table `pr_check_runs` with id, pr_id, check_name, conclusion, started_at, completed_at, duration_s, run_attempt
- [x] Unique constraint on `(pr_id, check_name, run_attempt)`
- [x] Indexes on `pr_id` and `check_name`

### backend/app/services/github_sync.py (extend)
- [x] Capture `head_sha` from `pr_data.get("head", {}).get("sha")` in `upsert_pull_request()`
- [x] After PR files sync, fetch check runs via `GET /repos/{full_name}/commits/{head_sha}/check-runs`
- [x] `upsert_check_run()` function with SELECT-then-create upsert pattern
- [x] Graceful error handling (logs warning on HTTP failure, continues sync)

### backend/app/services/stats.py (extend)
- [x] `get_ci_stats(session, date_from, date_to, repo_id=None)` function
- [x] `prs_merged_with_failing_checks` — subquery counting merged PRs with any failing check
- [x] `avg_checks_to_green` — average max run_attempt where conclusion=success
- [x] `flaky_checks` — check names with >10% failure rate (minimum 5 runs)
- [x] `avg_build_duration_s` — average duration across all check runs
- [x] `slowest_checks` — top 5 by average duration

### backend/app/schemas/schemas.py (extend)
- [x] `FlakyCheck` schema (name, failure_rate, total_runs)
- [x] `SlowestCheck` schema (name, avg_duration_s)
- [x] `CIStatsResponse` envelope schema

### backend/app/api/stats.py (extend)
- [x] `GET /api/stats/ci` route (admin-only, date_from/date_to/repo_id params)

### Frontend
- [x] `CIStatsResponse`, `FlakyCheck`, `SlowestCheck` TypeScript interfaces
- [x] `useCIStats` TanStack Query hook with optional repo filter
- [x] `CIInsights` page with StatCards, flaky checks table, slowest checks table, repo dropdown
- [x] Nav entry in Insights dropdown
- [x] Route registration in App.tsx

### Tests
- [x] 9 unit tests for `get_ci_stats()` (happy path, empty data, repo filter, flaky detection, date filtering, non-merged PRs)
- [x] 4 integration tests for `GET /api/stats/ci` (endpoint, repo filter, admin-only, empty)

## Rate Limit Note
Check runs API call is 1 per PR (for the HEAD SHA). Same rate-limit consideration as P3-06 (code churn). Only fetched when `head_sha` is present — existing PRs without it are skipped until next sync populates it.

## Files Created
- `backend/migrations/versions/010_add_pr_check_runs.py`
- `backend/tests/unit/test_ci_stats.py`
- `backend/tests/integration/test_ci_stats_api.py`
- `frontend/src/pages/insights/CIInsights.tsx`

## Files Modified
- `backend/app/models/models.py` — Added `PRCheckRun` model, `head_sha` + `check_runs` relationship on `PullRequest`
- `backend/app/schemas/schemas.py` — Added `FlakyCheck`, `SlowestCheck`, `CIStatsResponse`
- `backend/app/services/github_sync.py` — `head_sha` capture, `upsert_check_run()`, check-run fetch in `sync_repo()`
- `backend/app/services/stats.py` — `get_ci_stats()` function
- `backend/app/api/stats.py` — `GET /api/stats/ci` route
- `frontend/src/utils/types.ts` — `CIStatsResponse`, `FlakyCheck`, `SlowestCheck` interfaces
- `frontend/src/hooks/useStats.ts` — `useCIStats` hook
- `frontend/src/components/Layout.tsx` — CI/CD entry in Insights nav dropdown
- `frontend/src/App.tsx` — Route for `/insights/cicd`
- `CLAUDE.md` — Updated schema count, file trees, endpoint table, sync flow, patterns, completed tasks
