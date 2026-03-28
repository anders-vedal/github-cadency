# Task P3-04: Issue Creator Analytics (Management Friction Feedback)

## Phase
Phase 3 — Make It Proactive

## Status
done

## Blocked By
- P3-03-issue-quality-scoring
- P2-04-issue-pr-linkage

## Blocks
- P3-04b-ai-creator-stats-integration (deferred AI integration)

## Description
Add per-creator issue quality analytics so team leads and managers can see how well their task definitions serve developers. This is a **unique differentiator** — no competitor helps management see when their own process is causing friction. "Issues you create without checklists take 2.3x longer to close."

## Deliverables

- [x] **backend/app/services/stats.py** — `get_issue_creator_stats()` batch function returning all creators with metrics + team averages. Includes `_compute_creator_metrics()`, `_compute_team_averages()`, `_empty_creator_stats()` helpers.
- [x] **backend/app/api/stats.py** — `GET /api/stats/issues/creators` (admin-only, `team`/`date_from`/`date_to` query params)
- [x] **backend/app/schemas/schemas.py** — `IssueCreatorStats` + `IssueCreatorStatsResponse` Pydantic models
- [x] **frontend/src/utils/types.ts** — `IssueCreatorStats` + `IssueCreatorStatsResponse` TypeScript interfaces
- [x] **frontend/src/hooks/useStats.ts** — `useIssueCreatorStats()` TanStack Query hook
- [x] **frontend/src/pages/insights/IssueQuality.tsx** — Full Insights page with stat cards, creator table, red-badge highlighting, min-issue filter, team filter, methodology tooltips
- [x] **frontend/src/App.tsx** — Route `/insights/issue-quality`
- [x] **frontend/src/components/Layout.tsx** — Nav entry in Insights dropdown
- [x] **backend/tests/integration/test_issue_creator_api.py** — 7 integration tests
- [ ] **AI integration** — Deferred to P3-04b-ai-creator-stats-integration.md

## Deviations from Original Spec

1. **Batch endpoint instead of per-username**: Original spec called for `GET /api/stats/issues/creator/{github_username}`. Implemented as `GET /api/stats/issues/creators` (batch) returning all creators at once — the frontend table needs all creators in one request, and N+1 API calls would be wasteful.
2. **Extended schema**: Added `display_name`, `team`, `role` fields (via string join on `creator_github_username` → `Developer.github_username`) so the frontend can display creator identity and filter by team.
3. **Team averages**: Added `IssueCreatorStatsResponse.team_averages` field for frontend comparison/highlighting (>1.5x worse = red badge).
4. **Volume-based filtering**: Frontend applies a min-issue threshold (default 5) instead of any "creator role" concept — the data self-selects prolific issue creators.
5. **No FK migration**: Uses string join on `creator_github_username` rather than adding a `creator_id` FK column — avoids a migration for analytics-only queries.

## Files Created
- `backend/tests/integration/test_issue_creator_api.py`
- `frontend/src/pages/insights/IssueQuality.tsx`
- `.claude/tasks/improvements/P3-04b-ai-creator-stats-integration.md`

## Files Modified
- `backend/app/schemas/schemas.py`
- `backend/app/services/stats.py`
- `backend/app/api/stats.py`
- `frontend/src/utils/types.ts`
- `frontend/src/hooks/useStats.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/Layout.tsx`
- `CLAUDE.md`
- `docs/API.md`
