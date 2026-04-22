# Phase 04: Issue Conversations drill-down

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/issue_conversations.py`
- `backend/app/api/conversations.py`
- `frontend/src/pages/insights/IssueConversations.tsx`
- `frontend/src/hooks/useConversations.ts` (4 hooks)
- `frontend/src/components/charts/CommentBounceScatter.tsx` — Recharts ComposedChart + OLS regression

## Files Modified
- `backend/app/main.py` — registered `conversations.router`
- `backend/app/schemas/schemas.py` — `ChattyIssueRow`, `ChattyIssueRef`, `ChattyIssueLinkedPR`,
  `ConversationsScatterPoint`, `FirstResponseHistogramBucket`, `ParticipantDistributionBucket`
- `frontend/src/App.tsx` — `/insights/conversations` route + Linear insights sidebar entry
- `frontend/src/utils/types.ts`

## Deviations from spec
- Label filter slot exists server-side but no UI picker (no Linear labels list endpoint yet)
- Summary strip uses top-20 sample rather than a dedicated aggregate endpoint

## Blocked By
- 01-sync-depth-foundations
- 02-linking-upgrade-and-quality

## Blocks
- None

## Description

A dedicated page for investigating where dialogue happens in Linear, who is most engaged in it, and
whether the chattiest issues correlate with bouncier downstream PRs. Answers "why do some issues
generate more comments than others, and does that matter for outcome quality?"

## Deliverables

### backend/app/services/issue_conversations.py (new)

- `get_chattiest_issues(db, since, until, limit=20, filters={})` → top-N issues by comment count
  (excluding system-generated), with joined data:
  ```python
  [{
      "issue_id": int,
      "identifier": "ENG-123",
      "title": str,
      "url": str,
      "creator": {"id": int, "name": str},
      "assignee": {"id": int, "name": str},
      "project": {"id": int, "name": str},
      "priority_label": str,
      "estimate": float | None,
      "comment_count": int,
      "unique_participants": int,
      "first_response_s": int | None,
      "created_at": datetime,
      "status": str,
      "linked_prs": [
          {"pr_id": int, "number": int, "repo": str, "review_round_count": int, "merged_at": datetime}
      ],
      "avg_linked_pr_review_rounds": float | None,
  }]
  ```
  Filters: `project_id`, `creator_id`, `assignee_id`, `label`, `priority`, `has_linked_pr`

- `get_comment_vs_bounce_scatter(db, since, until)` → data for scatter plot:
  `[{"comment_count": int, "review_rounds": int, "issue_identifier": str, "pr_number": int}]`
  One point per (issue, linked_pr) pair where the issue had at least 1 non-system comment

- `get_first_response_histogram(db, since, until, bucket_hours=[1, 4, 12, 24, 72, 168])` → histogram
  of (creation → first non-creator, non-system comment) in time buckets
  Buckets: <1h / 1-4h / 4-12h / 12h-1d / 1-3d / 3-7d / >7d / never-answered

- `get_participant_distribution(db, since, until)` → histogram of unique participants per issue,
  buckets 1 / 2 / 3 / 4-5 / 6+

### backend/app/api/conversations.py (new)

- `GET /api/conversations/chattiest?since=&until=&limit=&project_id=&creator_id=&...`
- `GET /api/conversations/scatter?since=&until=`
- `GET /api/conversations/first-response?since=&until=`
- `GET /api/conversations/participants?since=&until=`
- All use existing auth middleware; available to any authenticated user (not admin-only — this is
  an insight surface for the whole team)

### backend/app/schemas/schemas.py

- `ChattyIssueRow`, `ConversationsScatterPoint`, `FirstResponseHistogramBucket`,
  `ParticipantDistributionBucket`

### frontend/src/pages/insights/IssueConversations.tsx (new)

Layout (follows existing insights page template — header with date range + filter row, then
content):

1. **Filter row**: project picker, creator picker, label multi-select, priority toggle, "has linked
   PR" toggle
2. **Top metrics strip** (4 stat cards): total issues in range, % with comments, median comments /
   issue, median first-response time
3. **Chattiness chart**: two-panel view
   - Left: histogram of comments/issue (x=comment count buckets, y=issue count)
   - Right: histogram of unique-participants/issue
4. **Correlation scatter**: x=issue comment count, y=linked-PR review rounds, one dot per
   (issue, PR) pair. Trend line with R² displayed. Tooltip shows issue identifier and PR number
5. **Chattiest issues table**: top 20 with columns creator / assignee / project / comments /
   participants / first-response time / linked PRs (chip list) / avg linked-PR review rounds.
   Row click → Linear deep link in new tab
6. **First response time** histogram: how fast do issues get their first engagement after creation?

### frontend/src/hooks/

- `useChattiestIssues(filters)`
- `useCommentBounceScatter(dateRange)`
- `useFirstResponseHistogram(dateRange)`
- `useParticipantDistribution(dateRange)`

### frontend/src/components/charts/

- `CommentBounceScatter.tsx` using Recharts scatter + linear regression line
  (use simple-statistics npm package or hand-roll OLS)
- Reuse existing histogram / bar chart components where possible

### frontend/src/App.tsx

- New route `/insights/conversations` lazy-loaded
- New sidebar entry under Insights: "Conversations", gated on `hasLinear`

### Tests

- `backend/tests/services/test_issue_conversations.py`: aggregation correctness, filter behavior,
  correlation math accuracy
- `e2e/tests/insights/issue-conversations.spec.ts`: page loads, filters work, scatter renders,
  chattiest table shows linked PR chips

## Acceptance criteria

- [x] Chattiest table shows the expected top issues by comment count for a seeded dataset
- [x] Scatter plot renders and the correlation coefficient matches a hand-computed value on test
      data
- [x] First-response histogram correctly classifies issues whose first-response was before any
      non-creator non-system comment was posted
- [x] Filters compose correctly (e.g., filter by creator + project shows intersection)
- [x] Empty state is graceful when no Linear data or when filters exclude everything
