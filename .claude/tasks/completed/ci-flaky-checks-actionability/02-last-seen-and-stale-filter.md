# Phase 02: Last-seen column + stale filter

**Status:** Completed
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** small
**Parent:** ci-flaky-checks-actionability/00-overview.md

## Scope

Checks linger in the date window after they've been renamed or removed because old PRs
still carry references to the old check names. They pollute the broken/flaky list with
no way to dismiss them. Surface a "last seen" date per row and default-hide checks that
haven't run in the last N days, with a toggle to show all.

## Backend

- `backend/app/schemas/schemas.py` — add `last_run_at: datetime | None` to `FlakyCheck`.
- `backend/app/services/stats.py` (`get_ci_stats`) — extend the `check_stats_q` SELECT
  with `func.max(PRCheckRun.created_at).label("last_run_at")` (or whichever timestamp
  column on `PRCheckRun` represents the run time — verify in `models/models.py`). Pass
  through into the `FlakyCheck(...)` constructor.
- No change to the `>10%` rate threshold or `≥5` runs threshold — staleness is presented
  as data and filtered client-side, not used to drop rows server-side. (Keeps the API
  honest: API shows what exists, frontend decides what's worth displaying.)

## Frontend

- `frontend/src/utils/types.ts` — add `last_run_at: string | null`.
- `frontend/src/pages/insights/CIInsights.tsx`:
  - Add a "Last Seen" column to the broken + flaky tables, formatted as relative time
    (`2 days ago`, `3 weeks ago`) — there's likely a helper in `frontend/src/utils/`,
    grep for `formatRelative|timeAgo|toRelativeTime`.
  - Add a `Show stale (>7 days)` toggle (checkbox or switch) in the card header. Default
    `false` — i.e., default-hide rows where `last_run_at` is older than 7 days from
    today. When toggled on, show all rows.
  - If filtering hides every row in a section, replace with the empty-state copy
    ("No flaky checks active in the last 7 days. Toggle 'Show stale' to include older
    runs.").
  - Stale rows when shown should be visually de-emphasized (`text-muted-foreground` or
    similar) so they don't draw attention.

## Tests

- Backend: extend the CI stats test with a fixture row whose latest `PRCheckRun` is 30
  days old → assert `last_run_at` is populated correctly.
- Frontend: not strictly required (no e2e for this card today — verify via existing
  smoke if it runs the page, otherwise manual).

## Acceptance

- Each row shows a "Last Seen" column with relative time.
- Rows with `last_run_at` older than 7 days are hidden by default.
- A toggle reveals stale rows with reduced visual weight.
- The empty-state copy explains the toggle so users don't think the data is missing.

## Blocked By

- None.

## Blocks

- None.

## Files Modified

- `backend/app/schemas/schemas.py` — added `last_run_at: datetime | None = None` to `FlakyCheck`.
- `backend/app/services/stats.py` — `check_stats_q` now aggregates `func.max(func.coalesce(started_at, completed_at))` per check name; value threaded through into `FlakyCheck(...)`. `PRCheckRun` has no `created_at`, so we fall back across the two timestamp columns.
- `frontend/src/utils/types.ts` — added `last_run_at: string | null` to the `FlakyCheck` interface.
- `frontend/src/pages/insights/CIInsights.tsx`:
  - Added `Show stale (>7 days)` Switch in the card header (default off).
  - Extracted shared `CheckHealthTable` sub-component so both Broken and Flaky sections render the same 4-column layout (Check Name / Failure Rate / Total Runs / Last Seen).
  - Client-side filter: rows with `last_run_at` older than 7 days (or null) are hidden by default. When `showStale` is on, all rows show, and stale rows get `text-muted-foreground opacity-70` plus a neutralized rate color so they don't draw attention.
  - When the filter empties every row, the card shows copy explaining the toggle: *"No flaky checks active in the last 7 days. Toggle 'Show stale' to include older runs."*
  - Footnote line shows "*N stale checks hidden*" when the filter is hiding rows, matching the spec's intent that users shouldn't think the data is missing.
- `backend/tests/unit/test_ci_stats.py` — `test_flaky_check_detection` extended to populate `started_at` and assert `last_run_at` matches the latest. New `test_last_run_at_reflects_stale_check` covers a check whose latest run is 30 days old.

## Verification

- 12/12 `tests/unit/test_ci_stats.py` pass; 4/4 integration tests pass.
- `pnpm exec tsc --noEmit` clean.
- Stale logic tested: `isStale(last_run_at, now)` treats null as stale (defensive — pre-existing rows without run timestamps shouldn't appear in the default view).

## Deviations from spec

- Spec mentioned `PRCheckRun.created_at` as a possible timestamp column; that column does not exist on the model. Implementation uses `coalesce(started_at, completed_at)` instead. Decision recorded here because any future timestamp work on `PRCheckRun` will want to know the model's shape up front.
