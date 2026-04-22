# Phase 04: Frontend gating + spec-compliance wiring

**Status:** completed
**Priority:** Medium
**Type:** bugfix
**Apps:** devpulse
**Effort:** small
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- None

## Blocks
- None

## Description

Frontend pages mount Linear-backed queries before checking `hasLinear`, producing ~19 wasted
requests per mount on installs without Linear. Plus three small spec-compliance deviations:
a non-clickable signal row, a Worker-visibility gate stricter than spec, and a creator-metrics
extension that never flowed into benchmarks.

## Deliverables

### `frontend/src/pages/insights/IssueConversations.tsx` — gate sub-queries on `hasLinear`

**Bug** (lines 104-113): `useChattiestIssues`, `useCommentBounceScatter`,
`useFirstResponseHistogram`, `useParticipantDistribution` all fire unconditionally. The
`hasLinear` guard at line 133 only affects render, not network.

**Fix**: pass `enabled: !!hasLinear` to each hook. Check the hook signatures in
`frontend/src/hooks/useConversations.ts`; add an `enabled?: boolean` parameter and forward to
TanStack's `useQuery` options. Default `true` to preserve behavior elsewhere.

### `frontend/src/pages/insights/FlowAnalytics.tsx` — gate sub-queries on `hasLinear`

**Bug** (lines 124-129): same pattern. `useFlowReadiness`, `useStatusTimeDistribution`,
`useStatusRegressions`, `useTriageBounces`, `useRefinementChurn` fire unconditionally.

**Fix**: same approach — extend hooks in `useFlowAnalytics.ts` to accept `enabled` and pass
`enabled: !!hasLinear` from the page.

### `frontend/src/pages/insights/Bottlenecks.tsx` — gate sub-queries on `hasLinear`

**Bug** (lines 76-86): 10 hooks fire unconditionally:
`useBottleneckSummary`, `useCumulativeFlow`, `useWip`, `useReviewLoad`, `useReviewNetwork`,
`useCrossTeamHandoffs`, `useBlockedChains`, `useReviewPingPong`, `useBusFactorFiles`,
`useCycleHistogram`.

**Fix**: extend `useBottlenecks.ts` hooks to accept `enabled`, pass `enabled: !!hasLinear`
from the page. The summary endpoint returns a synthesis; if it has value standalone it can
stay ungated, but the rest should gate.

### `frontend/src/components/linear-health/LinearUsageHealthCard.tsx` — creator-outcome drill-down link

**Bug** (lines 181-198): the Creator Outcome signal row is rendered as a plain `<div>`. The
spec calls for drill-down to `/insights/creator-analytics` (which today is the Insights →
Developer roster; adjust target if the actual route is different — check `App.tsx` for the
correct path).

**Fix**: wrap the row in `<Link to="...">` (or use the existing `<SignalRow>` pattern with a
`to` prop, matching the other four signals on this card). Verify dark-mode + hover states
match the other rows.

### `backend/app/api/developers.py` — Worker endpoint peer visibility

**Spec deviation** (line 279): the Worker endpoint enforces `_assert_self_or_admin`. Spec says
Worker is peer-visible when Linear is primary (Creator + Shepherd are the privileged ones).
Inline comment at line 278 says "matches spec" which is incorrect.

**Fix**:
1. Remove `_assert_self_or_admin` from the Worker endpoint.
2. Add a lightweight authorization check: user must be authenticated and Linear must be the
   primary issue source. If Linear is not primary, return 409 (matches the pattern for
   non-applicable endpoints).
3. Update the inline comment to reflect the actual gating logic.
4. `frontend/src/pages/DeveloperDetail.tsx`: remove `(isAdmin || isOwnPage)` from the Worker
   section guard (keep `isLinearPrimary`). Leave Creator and Shepherd gates as-is.
5. Add an API test that a non-admin user can GET `/api/developers/{other_id}/linear/worker`
   (200), but GETs on `/linear/creator` and `/linear/shepherd` for another developer return
   403.

### `backend/app/services/stats.py` — propagate creator metrics to benchmarks

**Gap**: `_get_issue_creator_stats_linear` computes `avg_downstream_pr_review_rounds` and
`sample_size_downstream_prs` correctly (Phase 05 deviation follow-up). But
`_compute_per_developer_metrics` was not extended to emit these fields, so they never flow
into the benchmark percentile engine. Benchmarks show older metrics only.

**Fix**:
1. Extend `_compute_per_developer_metrics` to compute the two new fields per developer when
   Linear is primary. Reuse the same sample-size-weighted logic.
2. Verify the new metrics appear in the `/api/benchmarks/*` responses.
3. Add an integration test that seeds creators with known review-rounds, calls the
   benchmarks endpoint, and asserts the aggregated percentile matches hand-computed.

## Acceptance criteria

- [x] Mounting `/insights/conversations`, `/insights/flow`, or `/insights/bottlenecks` on an
      install without Linear issues zero Linear-scoped network requests
- [x] Creator Outcome signal row is clickable and navigates to the creator analytics page
- [x] Worker endpoint returns 200 for non-admin peer requests (when Linear is primary); 409
      when Linear is not primary; other Linear-profile endpoints remain self/admin-only
- [x] Team benchmarks include `avg_downstream_pr_review_rounds` and
      `sample_size_downstream_prs`; an integration test locks the computation

## Implementation notes

- Every Linear-scoped hook in `useConversations.ts`, `useFlowAnalytics.ts`, and
  `useBottlenecks.ts` now accepts an `{ enabled?: boolean }` options bag and forwards
  it to TanStack Query. Pages pass `{ enabled: !!hasLinear }`; the gate is cheap and
  default-true to avoid changing behaviour on other callers.
- Creator Outcome row now drills into `/insights/issue-quality` (the nearest existing
  creator-analytics surface). Keeps the `<SignalRow>` look by using the same `<Link>`
  + hover-treatment wrapper as the other four rows.
- Worker endpoint (`/api/developers/{id}/linear-worker-profile`) dropped
  `_assert_self_or_admin` in favor of a plain `get_current_user` auth check +
  409 when Linear isn't the primary issue source. Creator + Shepherd endpoints
  remain self/admin-only — those carry more sensitive signal.
- `_compute_per_developer_metrics` in `stats.py` gained Batch 11:
  `avg_downstream_pr_review_rounds` and `sample_size_downstream_prs` per creator when
  Linear is primary. Mirrors the per-creator logic in
  `_get_issue_creator_stats_linear` so benchmark percentiles line up with the
  per-creator detail surface.

## Files Modified

- `frontend/src/hooks/useConversations.ts`
- `frontend/src/hooks/useFlowAnalytics.ts`
- `frontend/src/hooks/useBottlenecks.ts`
- `frontend/src/pages/insights/IssueConversations.tsx`
- `frontend/src/pages/insights/FlowAnalytics.tsx`
- `frontend/src/pages/insights/Bottlenecks.tsx`
- `frontend/src/pages/DeveloperDetail.tsx` (Worker-section peer visibility)
- `frontend/src/components/linear-health/LinearUsageHealthCard.tsx` (Creator Outcome
  drill-down Link)
- `backend/app/api/developers.py` (Worker endpoint gating)
- `backend/app/services/stats.py` (`_compute_per_developer_metrics` Batch 11)
