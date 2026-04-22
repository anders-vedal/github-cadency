# Phase 06: Flow analytics from history

**Status:** Completed (2026-04-22)
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/flow_analytics.py` — `get_status_time_distribution`,
  `get_status_regressions`, `get_triage_bounces`, `get_refinement_churn`,
  `has_sufficient_history`
- `backend/app/api/flow.py` — 5 endpoints under `/api/flow/*`
- `frontend/src/pages/insights/FlowAnalytics.tsx`
- `frontend/src/hooks/useFlowAnalytics.ts` (5 hooks)

## Files Modified
- `backend/app/main.py` — registered `flow.router`
- `backend/app/schemas/schemas.py` — `StatusTimeDistribution`, `StatusRegression`,
  `TriageBounce`, `RefinementChurnResponse`, `RefinementChurnRow`, `RefinementChurnDistribution`,
  `FlowReadinessResponse`
- `frontend/src/App.tsx` — `/insights/flow` route + Linear insights sidebar entry
- `frontend/src/utils/types.ts`

## Deviations from spec
- No new `feature_toggles` table — readiness gate at `/api/flow/readiness` drives the
  UI show/hide directly (thresholds: 14 days + 100 issues, tunable via module constants)

## Blocked By
- 01-sync-depth-foundations

## Blocks
- 07-bottleneck-intelligence

## Description

Turn the new `external_issue_history` table into a workflow lens: time spent in each status, status
regressions, triage bounces, and refinement churn. These signals expose where work gets stuck in the
flow — before PR review, before implementation even starts. Only meaningful after enough history has
accumulated (weeks, not days), so the UI ships behind a feature flag that auto-enables once coverage
crosses a threshold.

## Deliverables

### backend/app/services/flow_analytics.py (new)

- `get_status_time_distribution(db, since, until, group_by="all|project|team")` →
  For each status category (triage/todo/in_progress/in_review/done/cancelled), percentile time in
  state (p50/p75/p90/p95). Computed by walking `external_issue_history` for each issue and diffing
  consecutive status changes

- `get_status_regressions(db, since, until)` → issues that went backwards:
  in_progress → todo, in_review → in_progress, done → in_progress.
  Returns per-issue rows with the regression transition and timestamp.
  Aggregate: total regressions per project, per assignee, per creator — who's sending work back?

- `get_triage_bounces(db, since, until)` → issues that left triage then came back:
  `(transitioned out of triage) AND later (transitioned into triage)` = unclear scope signal

- `get_refinement_churn(db, since, until)` → for each issue, count the number of
  estimate / priority / project changes between created_at and started_at (or `current time` if
  not started). High churn = unsettled scope before work began.
  Aggregate: distribution (p50/p90), outliers (top 20)

- `has_sufficient_history(db)` → boolean + stats:
  ```python
  {
      "ready": bool,
      "days_of_history": int,
      "issues_with_history": int,
      "threshold_days": 14,
      "threshold_issues": 100,
  }
  ```
  UI uses this to decide whether to show the page or a "not enough data yet" state

### backend/app/api/flow.py (new)

- `GET /api/flow/status-distribution?since=&until=&group_by=`
- `GET /api/flow/regressions?since=&until=`
- `GET /api/flow/triage-bounces?since=&until=`
- `GET /api/flow/refinement-churn?since=&until=`
- `GET /api/flow/readiness` — returns `has_sufficient_history` result

### backend/app/schemas/schemas.py

- `StatusTimeDistribution`, `StatusRegression`, `TriageBounce`, `RefinementChurnRow`, `FlowReadiness`

### frontend/src/pages/insights/FlowAnalytics.tsx (new)

Layout:
1. **Readiness banner** — if insufficient history, show "Flow analytics needs ~14 days of history;
   you have X. Page will unlock automatically"
2. **Status time heatmap** — stacked bar or heatmap: one row per status, length represents median
   time in state; color represents p90 / p50 ratio (wide spread = volatile)
3. **Status regressions** — table of issues that bounced backwards, sortable by count. Click → Linear
4. **Triage quality** — bar chart of issues that re-entered triage grouped by creator; list of
   offending issues
5. **Refinement churn** — histogram of churn-events-per-issue. Top-20 table of churn-iest issues
   for drill-down

### frontend/src/hooks/

- `useFlowReadiness()`, `useStatusTimeDistribution(dateRange, groupBy)`,
  `useStatusRegressions(dateRange)`, `useTriageBounces(dateRange)`, `useRefinementChurn(dateRange)`

### frontend/src/App.tsx

- New route `/insights/flow` lazy-loaded
- Sidebar entry "Flow Analytics", gated on `hasLinear && isPrimary`. The entry is visible even
  when readiness is false; the page itself shows the readiness banner — helps set expectations

### Feature flag

- New `flow_analytics` entry in the existing `ai_feature_toggles` pattern or a new
  `feature_toggles` mechanism if one doesn't exist for non-AI features. Default ON for installations
  where `has_sufficient_history == true`, OFF otherwise, admin can force on/off

### Tests

- `backend/tests/services/test_flow_analytics.py`: status duration math, regression detection,
  triage bounce detection, refinement churn counts against seeded history
- E2E test: page loads; if insufficient history banner renders; if sufficient, all four sections
  render with expected signals from seeded data

## Acceptance criteria

- [x] Status duration math correctly handles issues with no history (single row in history table —
      treat as still-in-initial-status)
- [x] Regression detection identifies the seeded backwards transitions exactly
- [x] Triage bounce detection catches the seeded "out-and-back-to-triage" cases
- [x] Refinement churn counts increment on estimate / priority / project changes and ignore other
      field changes (e.g. label changes are not churn)
- [x] Readiness gating hides the page when history is thin, with a helpful explanation
- [x] Date range applied consistently — the "window" used for aggregation is the issue's activity
      window intersected with the selected range
