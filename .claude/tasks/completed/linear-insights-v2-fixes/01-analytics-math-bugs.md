# Phase 01: Analytics math bugs

**Status:** completed
**Priority:** High
**Type:** bugfix
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- None

## Blocks
- 07-missing-test-files

## Description

Six correctness bugs across Phase 01, 02, 04, and 06 services that silently produce wrong
numbers in the UI. Each fix is localized — the fixes do not interact with each other and can
be committed independently if useful.

## Deliverables

### `backend/app/services/linkage_quality.py` — `get_link_quality_summary` denominator

**Bug**: `total_prs` at lines 39-41 is `select(func.count(PullRequest.id))` with no integration
filter, while `linked_prs` IS scoped via a join through `PRExternalIssueLink →
ExternalIssue.integration_id`. On any install with >1 integration (or any repo outside the
Linear org), the displayed `linkage_rate` is badly wrong (denominator inflated).

**Fix**: when `integration_id` is provided, scope `total_prs` to PRs in repos that belong to
that integration. DevPulse's `Repository` table has `integration_id` — join through it. If
`integration_id` is None, retain current behavior (system-wide count).

Add a 1-line docstring note: "When `integration_id` is given, `total_prs` is restricted to PRs
in repositories belonging to that integration".

### `backend/app/services/linear_sync.py` — populate `triage_responsibility_team_id` and `triage_auto_assigned`

**Bug**: The `_ISSUES_FIELDS` GraphQL fragment omits `triageResponsibility { team { id }
autoAssigned }`. The columns exist in migration 042 and ship as always-NULL. Phase 01
acceptance criterion is unmet.

**Fix**:
1. Extend `_ISSUES_FIELDS` to include `triageResponsibility { team { id } autoAssigned }`.
2. In the issue-upsert loop in `sync_linear_issues`, extract the nested field (null-safe) and
   set `issue.triage_responsibility_team_id` and `issue.triage_auto_assigned`.
3. Add a unit test in `test_linear_sync_depth.py` that seeds a stub response with a
   `triageResponsibility` block and asserts both columns are populated.

### `backend/app/services/issue_conversations.py` — `get_chattiest_issues` label filter

**Bug**: At lines 66 and 82-85 the `.limit(limit)` is applied before the `label` filter. Label
filter then runs in Python on the already-limited 20-row slice. If the top-20-commented issues
don't carry the chosen label, the user sees 0 rows even when matching issues exist further
down the list.

**Fix**: Move the label filter into the SQL WHERE clause. `ExternalIssue.labels` is a JSON
column. For PostgreSQL use `ExternalIssue.labels.contains([label])` (JSONB containment). For
SQLite (test DB) the same operator works via `JSON` type's Python-side fallback. If the
operator doesn't work in tests, use a generic `func.json_each` or a cast + `ilike`; prefer the
cleaner JSONB path and add a SQLite-compatible fallback if the test suite needs it.

Keep the `has_linked_pr` filter post-fetch — that one requires a correlated lookup and is
correctly structured.

### `backend/app/services/linear_health.py` — `median_comments_before_first_pr` semantics

**Bug**: Lines 110-133 compute the median of total non-system comments for issues in range.
The field name and spec both describe "comments before first merged PR is created". The
computed value overstates pre-PR clarification cost because comments accumulate after the PR
merges on long-running issues.

**Fix (preferred — match the name)**: Restrict the comment count per issue to comments whose
`created_at <= first_linked_pr.created_at` (or `merged_at` if that matches the signal intent
better; check the spec at `.claude/tasks/linear-insights-v2/03-usage-health-dashboard.md`).
For issues without a linked PR, exclude from the median sample.

**Fallback (if scope matters)**: Rename the field to `median_comments_per_issue` in both the
service, Pydantic schema, and frontend `LinearUsageHealthCard.tsx`. Document the rename in the
PR description. The preferred fix is stronger; the fallback only if the pre-PR filter turns
out to be complex.

### `backend/app/services/flow_analytics.py` — `get_status_time_distribution` first-state + tail

**Bugs** (both in lines 119-147):
1. `prev_time = None` / `current_state = None` initial values mean the first event's
   `from_state` duration is never accumulated. Every issue loses its initial-state time
   (usually the largest bucket — time in triage or backlog before first transition).
2. No open-interval tail: after the loop, issues still in their current state contribute 0 to
   that state.

**Fix**:
1. Before the loop, seed `prev_time = since` and `current_state = from_cat` taken from the
   first event's `from_state_category`. The event sequence must be ordered by `changed_at`;
   verify the query's `order_by` clause.
2. After the loop, when `current_state` and `prev_time` are set, compute
   `delta = int((until - prev_time).total_seconds())` and append to
   `durations_by_state[current_state]` when `delta > 0`.
3. Add a test: an issue with a known history gives exact expected durations for each state,
   including the initial state and the trailing current state.

### `backend/app/services/developer_linear.py` — Worker profile date filter

**Bug**: Lines 150-157 filter by `ExternalIssue.created_at` in range. The spec says "issues
*started* or *completed* in range". Issues assigned mid-flight (created before the window,
finished within it) are silently excluded. Cycle time, triage-to-start, and self-picked% all
under-count on long-lived work.

**Fix**: Replace the `created_at` filter with:
```python
(
    ((ExternalIssue.started_at >= since) & (ExternalIssue.started_at <= until)) |
    ((ExternalIssue.completed_at >= since) & (ExternalIssue.completed_at <= until))
)
```

Check that both `started_at` and `completed_at` exist on `ExternalIssue`. If only one exists,
fall back to using issue state transitions via `ExternalIssueHistoryEvent` (last `started`
event, last `completed` event) — but the columns should already exist from Phase 01.

## Testing

Each fix above lists a specific regression test. All of them land in Phase 07 — which creates
`test_flow_analytics.py`, `test_issue_conversations.py`, and `test_developer_linear.py` — plus
additions to the existing `test_linear_sync_depth.py` (for the triage fields).

## Acceptance criteria

- [x] `get_link_quality_summary` returns correct `linkage_rate` when `integration_id` is
      provided on multi-repo installs
- [x] After a sync, `triage_responsibility_team_id` and `triage_auto_assigned` are populated
      on issues that have triage metadata in Linear
- [x] `get_chattiest_issues` with `label="foo"` returns every issue in range that has that
      label, ordered by comment count — never silently truncates
- [x] `median_comments_before_first_pr` either (a) correctly filters to pre-PR comments, or
      (b) is renamed to match what it computes
- [x] `get_status_time_distribution` correctly attributes the initial-state time and the
      trailing-state time; a test case with known ground truth matches exactly
- [x] Worker profile "Issues Worked" count includes long-lived issues that were started or
      completed in the window but created earlier

## Implementation notes

- `linkage_quality.get_link_quality_summary`: Repository lacks `integration_id` in the
  current schema (the task spec was inaccurate on this). Scoped `total_prs` by proxy:
  repos with at least one PR linked to this integration's issues — semantically matches
  "PRs in Linear-participating repos".
- `issue_conversations`: JSONB `.contains()` doesn't compile on SQLite (emits `@>` which
  aiosqlite rejects). Used portable `cast(labels, String).like('%"label"%')` instead so
  the filter works across PostgreSQL and the test DB.
- `linear_health._compute_spec_quality` now computes `median_comments_before_first_pr`
  from comments with `created_at <= first_linked_pr.created_at`; issues without a linked
  PR are excluded from the sample. `high_comment_issue_pct` keeps its prior computation
  (total non-system comments) so the 10% bucket logic is unaffected.
- `flow_analytics.get_status_time_distribution`: seeds `prev_time = since`, `current_state
  = events[0].from_state_category` and closes with a trailing interval to `until`, so
  initial-state and open-interval buckets are both accumulated.
- `developer_linear.get_developer_worker_profile`: filter switched to `or_(started_at in
  range, completed_at in range)`.

## Files Modified

- `backend/app/services/linkage_quality.py`
- `backend/app/services/linear_sync.py` (added `triageResponsibility` to `_ISSUES_FIELDS`
  and issue upsert)
- `backend/app/services/issue_conversations.py`
- `backend/app/services/linear_health.py`
- `backend/app/services/flow_analytics.py`
- `backend/app/services/developer_linear.py`
