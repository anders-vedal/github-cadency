# Task P2-01: Stale PR List Endpoint

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- 07-stats-service
- P1-07-draft-pr-filtering

## Blocks
- P2-08-workload-collaboration-pages

## Description
Add a dedicated endpoint returning open PRs that need attention, sorted by staleness. Currently, the workload service counts `prs_waiting_for_review` as a number but returns no list of which PRs are waiting, how long each has been open, or who is blocking them. A team lead needs: "which open PRs on my team need attention today?"

## Deliverables

- [x] **backend/app/schemas/schemas.py** — `StalePR` and `StalePRsResponse` Pydantic models
- [x] **backend/app/services/stats.py** — `get_stale_prs()` with 3 staleness categories (no_review, changes_requested_no_response, approved_not_merged), sorted by age descending
- [x] **backend/app/api/stats.py** — `GET /api/stats/stale-prs` route (admin-only, `team` + `threshold_hours` params)
- [x] **frontend/src/utils/types.ts** — `StalePR` and `StalePRsResponse` TypeScript interfaces
- [x] **frontend/src/hooks/useStats.ts** — `useStalePRs()` TanStack Query hook
- [x] **frontend/src/pages/Dashboard.tsx** — `StalePRsSection` component in "Needs Attention" zone with color-coded age and reason badges

## Deviations from Spec

- **No `date_from`/`date_to` params**: Stale PRs are a "right now" view of currently open PRs. Date range filtering was dropped as it adds complexity without value for this use case. Only `team` and `threshold_hours` are supported.
- **"No response" heuristic**: The `changes_requested_no_response` check uses a 1-hour tolerance window comparing `PR.updated_at` vs `review.submitted_at`. The comparison is done in Python rather than SQL for SQLite/PostgreSQL portability.

## Files Modified

- `backend/app/schemas/schemas.py`
- `backend/app/services/stats.py`
- `backend/app/api/stats.py`
- `frontend/src/utils/types.ts`
- `frontend/src/hooks/useStats.ts`
- `frontend/src/pages/Dashboard.tsx`
- `CLAUDE.md`
- `docs/API.md`

## Files Created

- `backend/tests/integration/test_stale_prs_api.py` (10 tests)
