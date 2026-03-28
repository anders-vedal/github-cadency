# Task P3-06: Code Churn Analysis (File-Level Change Tracking)

## Phase
Phase 3 — Make It Proactive

## Status
completed

## Blocked By
- 04-github-sync-service

## Blocks
- P4-01-dora-metrics

## Description
Track which files are changed by each PR to enable code churn analysis — identifying hotspots where bugs cluster, files with concentrated ownership (bus factor at file level), and areas of the codebase that may need refactoring. Also snapshots the full repo file tree via GitHub Trees API for stale directory detection.

## Deliverables

- [x] Database migration (`009_add_pr_files_and_repo_tree.py`)
  - New table: `pr_files` (id, pr_id, filename, additions, deletions, status, previous_filename)
  - New table: `repo_tree_files` (id, repo_id, path, type, last_synced_at)
  - New columns on `repositories`: `default_branch`, `tree_truncated`
- [x] ORM models: `PRFile`, `RepoTreeFile` with relationships
- [x] Sync service extensions (`github_sync.py`)
  - `upsert_pr_file()` — upserts file data per PR from GitHub PR files API
  - `sync_repo_tree()` — fetches full repo tree via GitHub Trees API (delete + re-insert snapshot)
  - `upsert_repo()` extended to save `default_branch`
  - `sync_repo()` extended to fetch PR files per PR and tree per repo
  - Error handling: `sync_repo_tree` failure does not abort entire repo sync
- [x] Stats service (`get_code_churn()`)
  - Hotspot files ranked by change frequency with contributor count
  - Stale directories: batch detection using top-level dir extraction (no N+1)
  - `tree_truncated` flag surfaced from Repository model
- [x] Schemas: `FileChurnEntry`, `StaleDirectory`, `CodeChurnResponse`
- [x] API route: `GET /api/stats/repo/{id}/churn` (admin only, query params: date_from, date_to, limit)
- [x] Frontend page: `/insights/code-churn` with repo selector, stat cards, hotspot table, stale directories table
- [x] Nav: added to Insights dropdown in Layout
- [x] Unit tests (8 tests): hotspot ranking, date range filtering, stale detection, file counts, empty repo, limit
- [x] Integration tests (6 tests): 404, empty repo, with files, stale dirs, limit, response shape

## Deviations from Original Spec
- Added `repo_tree_files` table (not in original spec) for full repo tree mapping and stale directory detection
- Added `default_branch` and `tree_truncated` columns to `repositories`
- `directories_with_no_changes` renamed to `stale_directories` with richer schema (file_count, last_pr_activity)
- Used `filename` instead of `path` as the column name on `pr_files` to avoid conflict with Python reserved usage
- Stale directory detection uses batch Python-side aggregation instead of per-directory SQL LIKE queries (eliminates N+1)
- Added `previous_filename` column for rename tracking
- Added simple frontend page (not in original spec which was backend-only)

## Files Created
- `backend/migrations/versions/009_add_pr_files_and_repo_tree.py`
- `backend/tests/unit/test_code_churn.py`
- `backend/tests/integration/test_code_churn_api.py`
- `frontend/src/pages/insights/CodeChurn.tsx`

## Files Modified
- `backend/app/models/models.py` — added PRFile, RepoTreeFile models + relationships on Repository and PullRequest
- `backend/app/services/github_sync.py` — added upsert_pr_file, sync_repo_tree; extended upsert_repo and sync_repo
- `backend/app/services/stats.py` — added get_code_churn function with _extract_top_dir helper
- `backend/app/schemas/schemas.py` — added CodeChurn schemas
- `backend/app/api/stats.py` — added churn endpoint + imports
- `frontend/src/utils/types.ts` — added CodeChurn TypeScript interfaces
- `frontend/src/hooks/useStats.ts` — added useCodeChurn hook
- `frontend/src/components/Layout.tsx` — added Code Churn to Insights nav dropdown
- `frontend/src/App.tsx` — added /insights/code-churn route
