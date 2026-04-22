# Phase 03: Linear Usage Health dashboard card

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/linear_health.py` — `get_linear_usage_health()` + `is_linear_primary()`
- `backend/app/api/linear_health.py` — `GET /api/linear/usage-health`
- `backend/tests/integration/test_linear_health.py` (8 tests)
- `frontend/src/components/linear-health/LinearUsageHealthCard.tsx`
- `frontend/src/components/linear-health/CreatorOutcomeMiniTable.tsx`
- `frontend/src/hooks/useLinearUsageHealth.ts`

## Files Modified
- `backend/app/main.py` — registered `linear_health.router`
- `backend/app/schemas/schemas.py` — `LinearUsageHealthResponse`, `LinearHealthAdoption`,
  `LinearHealthSpecQuality`, `LinearHealthAutonomy`, `LinearHealthDialogue`,
  `LinearHealthCreatorOutcome`, `LinearHealthCreatorRow`
- `frontend/src/pages/Dashboard.tsx` — inserted `LinearUsageHealthCard`, gated on
  `hasLinear && isLinearPrimary`
- `frontend/src/utils/types.ts` — Phase 03 types

## Blocked By
- 01-sync-depth-foundations
- 02-linking-upgrade-and-quality

## Blocks
- None

## Description

Add a narrative dashboard card answering "is Linear driving real work, or is it a ticket graveyard?"
in five signals. Sits on the main Dashboard page alongside existing cards, visible only when Linear
integration is active and is primary issue source.

## Deliverables

### backend/app/services/stats.py (or new linear_health.py)

New function `get_linear_usage_health(db, org_id=None, since=None, until=None)` returning:

```python
{
    "adoption": {
        "linked_pr_count": int,
        "total_pr_count": int,
        "linkage_rate": float,       # 0..1
        "target": 0.70,
        "status": "healthy|warning|critical",  # >=0.7 / 0.5-0.7 / <0.5
    },
    "spec_quality": {
        "median_description_length": int,     # chars at issue creation
        "median_comments_before_first_pr": float,
        "high_comment_issue_pct": float,      # % of issues in top 10% by comment count
        "status": "healthy|warning|critical",
    },
    "autonomy": {
        "self_picked_count": int,             # issues where creator == assignee
        "pushed_count": int,                  # creator != assignee
        "self_picked_pct": float,
        "median_time_to_assign_s": int,       # from first history event where assignee was set
    },
    "dialogue_health": {
        "median_comments_per_issue": float,
        "p90_comments_per_issue": int,
        "silent_issue_pct": float,            # % issues with 0 non-system comments
        "distribution_shape": "healthy|heavy_tailed|monomodal",
    },
    "creator_outcome": {
        "top_creators": [
            {
                "developer_id": int,
                "developer_name": str,
                "issues_created": int,
                "avg_comments_on_their_issues": float,
                "avg_downstream_pr_review_rounds": float,
                "sample_size": int,           # linked PRs — below 5 → low-confidence badge
            },
            ...
        ]
    }
}
```

- Source for adoption: `PRExternalIssueLink` count joined to `PullRequest` filtered by date range
- Source for spec quality: `ExternalIssue.description_length` + derived comment-count-before-merged-PR
- Source for autonomy: compare `creator_developer_id` vs `assignee_developer_id`; for time-to-assign,
  query `external_issue_history` for earliest event where `field='assignee' AND to_value IS NOT NULL`
- Source for dialogue health: `ExternalIssueComment` aggregation excluding `is_system_generated`
- Source for creator outcome: join `ExternalIssue` → `PRExternalIssueLink` → `PullRequest.review_round_count`,
  average per creator; guard with `sample_size >= 5`

Status rules documented in each function docstring; keep them tunable via constants at the top of
the module.

### backend/app/api/

- New router `backend/app/api/linear_health.py` OR add to existing `sprints.py`:
  - `GET /api/linear/usage-health?since=...&until=...` → `LinearUsageHealthResponse`
- Uses `get_current_user` + default date range helper (last 30 days)

### backend/app/schemas/schemas.py

- `LinearUsageHealthResponse` and nested schemas for each signal

### frontend/src/pages/Dashboard.tsx

- Add `<LinearUsageHealthCard />` to the Dashboard layout between the existing overview cards
- Only render when `hasLinear && isPrimary` (use `useIntegrations` to check); otherwise show a CTA
  to set Linear as primary

### frontend/src/components/linear-health/ (new folder)

- `LinearUsageHealthCard.tsx` — outer card with 5 mini-stat rows, one per signal, each with:
  - Icon (adoption: link-2, spec: file-text, autonomy: user-check, dialogue: message-square,
    creator-outcome: git-pull-request)
  - Headline number
  - Status pill (healthy green, warning amber, critical red)
  - One-line interpretation ("70% of merged PRs are linked to Linear — healthy")
  - Click-through to drill-down (adoption → Admin > Linkage Quality, spec → /insights/conversations,
    autonomy → /insights/planning, dialogue → /insights/conversations, creator → /insights/creator-analytics)
- `CreatorOutcomeMiniTable.tsx` — top-3 creators with their downstream PR bounce signal, framed as
  "Ticket clarity signal — who's shipping tickets that flow cleanly". Tooltip explains correlation
  and warns low-sample-size rows
- Tone: self-reflection, not leaderboard. Copy matters here — review with product before shipping

### frontend/src/hooks/

- `useLinearUsageHealth(dateRange)` — TanStack Query wrapper, 5 min stale time

### Tests

- `backend/tests/services/test_linear_usage_health.py`: each of the five signals computed against a
  seeded dataset (including edge cases: no issues, no comments, all bot comments, sample size < 5)
- `backend/tests/api/test_linear_health.py`: endpoint permissions, empty-state handling,
  admin vs developer view parity
- `e2e/tests/insights/linear-usage-health.spec.ts`: smoke-level test that the card renders with
  the five signals and click-throughs route correctly

## Acceptance criteria

- [x] Dashboard shows the new card when Linear is primary, hidden otherwise (via 409 path)
- [x] All five signals compute correctly against test data
- [x] Status pills match the documented thresholds
- [x] Creator→outcome table excludes low-sample-size rows or badges them clearly
- [ ] Copy framing is self-reflection, not comparative ranking (PM/design sign-off — pending review)
- [x] Empty state (no Linear data yet) has a graceful "run a sync to populate" message
