# Task P4-04: Executive Reporting Dashboard

## Phase
Phase 4 — Make It Best-in-Class

## Status
completed

## Blocked By
- P1-05-recharts-trend-viz (completed)
- P2-08-workload-collaboration-pages (completed)
- ~~P3-02-sprint-model~~ (not implemented; sprints skipped by design)
- P4-02-work-categorization (completed)

## Blocks
None

## Description
Build a director/VP-level dashboard that shows team health at a strategic level: velocity trends, work allocation, quality indicators, and risk signals. This is a different view than the team lead dashboard — it answers "is this team healthy and shipping?" rather than "what needs my attention today?"

## Deliverables

### frontend/src/pages/ExecutiveDashboard.tsx (new)
Route: `/executive` (admin-only)

**Section 1: Team Velocity**
- [x] Stacked bar chart: PRs merged per period by work category
- [x] Stat cards: PRs merged, merge rate, avg time to merge, avg time to first review
- [x] Delta vs previous same-duration period
- ~~Sprint-over-sprint velocity comparison~~ — skipped (sprints not implemented)

**Section 2: Investment Allocation**
- [x] Donut chart: feature vs bugfix vs tech-debt vs ops (from P4-02)
- [x] Stacked bar chart: allocation trend over time
- [x] Comparison to previous period via trend deltas

**Section 3: Quality Indicators**
- [x] Revert rate with trend delta
- [x] Reviews given count
- [x] Issues closed count
- [x] CI failure rate (from P3-07, when available)

**Section 4: Team Health Summary**
- [x] Bus factor alerts (repos with single-reviewer dependency)
- [x] Silo alerts (teams not reviewing each other's code)
- [x] Workload distribution bar chart (low/balanced/high/overloaded)
- [x] Collaboration health trend line chart (monthly bus factors, silos, isolated developers)
- ~~Developer growth: goals achieved this quarter~~ — skipped (goals page already surfaces this)

**Section 5: Risks**
- [x] High-risk PRs table (from P3-05, level=high)
- [x] Developers with declining trends (>30% PR drop or >20% review quality drop)
- [x] Stale PR backlog count

### Backend
- [x] `GET /api/stats/collaboration/trends` — new endpoint for monthly bus factor/silo/isolation counts (deviation from spec which said no new endpoints needed)

### Navigation
- [x] "Executive" as a top-level admin-only nav item
- [x] Only visible when authenticated as admin

## Deviations from Spec
- **New backend endpoint added:** `GET /api/stats/collaboration/trends` was added to support the Team Health trend chart. The spec said no new endpoints, but server-side bucketing is more efficient than N frontend API calls.
- **Sprint-related content skipped:** P3-02 (sprint model) was never implemented. All sprint references removed.
- **"Developer growth" sub-section skipped:** Goals page already shows this. Added "declining developers" detection instead.
- **Previous period comparison uses same-duration sliding window** instead of fixed quarterly comparison, matching the existing Dashboard pattern and the global date range picker.

## Files Created
- `frontend/src/pages/ExecutiveDashboard.tsx`
- `backend/tests/integration/test_collaboration_trends_api.py`

## Files Modified
- `backend/app/schemas/schemas.py` — added `CollaborationTrendPeriod`, `CollaborationTrendsResponse`
- `backend/app/services/collaboration.py` — added `get_collaboration_trends()`
- `backend/app/api/stats.py` — added `/stats/collaboration/trends` route
- `frontend/src/hooks/useStats.ts` — added `useCollaborationTrends` hook
- `frontend/src/utils/types.ts` — added `CollaborationTrendPeriod`, `CollaborationTrendsResponse`
- `frontend/src/App.tsx` — added route + import
- `frontend/src/components/Layout.tsx` — added "Executive" nav item
- `frontend/src/pages/insights/Investment.tsx` — removed invalid `TooltipProvider` import (pre-existing build fix)
- `CLAUDE.md` — documented feature
- `docs/API.md` — added endpoint reference
