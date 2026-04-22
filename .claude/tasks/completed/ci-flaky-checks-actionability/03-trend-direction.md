# Phase 03: Trend direction indicator

**Status:** Completed
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** small
**Parent:** ci-flaky-checks-actionability/00-overview.md

## Scope

A flake getting worse is more urgent than one fading out. Compute the failure rate for
the first half and second half of the date window per check, and show an arrow per row
indicating direction.

## Backend

- `backend/app/schemas/schemas.py` — add to `FlakyCheck`:
  - `failure_rate_first_half: float | None`
  - `failure_rate_second_half: float | None`
  - `trend: Literal["rising", "falling", "stable"] | None` (None when one half has fewer
    than 3 runs — too small to call a trend)
- `backend/app/services/stats.py` (`get_ci_stats`):
  - Compute `midpoint = date_from + (date_to - date_from) / 2`.
  - For each check_name retained in the result set, run an additional aggregate (or fold
    into the existing `check_stats_q` with conditional sums) computing failure rate for
    `created_at < midpoint` and `created_at >= midpoint` separately.
  - Classify trend: `rising` if `second_half - first_half >= 0.10`, `falling` if
    `first_half - second_half >= 0.10`, else `stable`. None if either half has `<3`
    runs.
  - Two reasonable implementations — pick whichever reads cleaner:
    1. Extend `check_stats_q` with four conditional `func.sum(case(...))` aggregates
       (first_half_runs, first_half_failures, second_half_runs, second_half_failures)
       in one query.
    2. Issue a small follow-up query per check after filtering the >10% set. Fewer
       checks means few extra queries; might be more readable.

## Frontend

- `frontend/src/utils/types.ts` — add the three new fields.
- `frontend/src/pages/insights/CIInsights.tsx`:
  - Add a "Trend" column between "Failure Rate" and "Total Runs" (or however the
    layout reads best).
  - Render an arrow icon from `lucide-react`:
    - `rising` → `TrendingUp` red, tooltip showing `{first}% → {second}%`
    - `falling` → `TrendingDown` green, same tooltip format
    - `stable` → `Minus` muted
    - `null` → em-dash, tooltip "Not enough data in one half of the window to compute a
      trend"
  - Tooltip on hover shows both halves rounded to one decimal.

## Tests

- Backend: extend the CI stats test with a check that has 10 runs in the first half (8
  failures = 80%) and 10 runs in the second half (2 failures = 20%) → assert
  `trend == "falling"` and the half rates are populated.
- Add a case where one half has only 2 runs → assert `trend is None`.

## Acceptance

- Each row shows a trend arrow with a tooltip showing first-half vs second-half failure
  rate.
- Trend is `null` (em-dash) when sample is too small in either half — never invented.
- Rising trends are visually distinct from falling.

## Blocked By

- None.

## Blocks

- None.

## Files Modified

- `backend/app/schemas/schemas.py` — added three additive fields to `FlakyCheck`:
  `failure_rate_first_half`, `failure_rate_second_half`, `trend` (`"rising" | "falling" | "stable" | None`).
- `backend/app/services/stats.py` — `get_ci_stats` computes `midpoint = date_from + (date_to - date_from) / 2` and extends `check_stats_q` with four conditional sums (`first_half_runs`, `first_half_failures`, `second_half_runs`, `second_half_failures`). Trend classification happens in Python after the query:
  - `None` when either half has `<3` runs (too small to call).
  - `rising` when `second - first >= 0.10`.
  - `falling` when `first - second >= 0.10`.
  - `stable` otherwise.
  Chose the single-query extension (implementation option 1 in the spec) over per-check follow-up queries — keeps the flow readable and avoids N extra round-trips.
- `frontend/src/utils/types.ts` — added the three new fields to the `FlakyCheck` type.
- `frontend/src/pages/insights/CIInsights.tsx`:
  - New `TrendCell` sub-component renders `TrendingUp` (red), `TrendingDown` (green), `Minus` (muted), or em-dash for `null`, each with a tooltip showing `{first}% → {second}%` (or the "not enough data" copy for `null`).
  - Added a "Trend" column between "Failure Rate" and "Total Runs" in `CheckHealthTable`; `TableSkeleton` column count bumped to 5.
  - Icons carry `aria-label` for screen readers: e.g., *"Failure rate falling: 80.0% → 20.0%"*.
- `backend/tests/unit/test_ci_stats.py`:
  - `test_trend_falling` — 10 first-half runs (80% failure) + 10 second-half runs (20% failure) → `trend == "falling"`.
  - `test_trend_insufficient_sample_returns_none` — 5 first-half runs + 2 second-half runs → `trend is None`, both half-rates `None`.

## Verification

- 14/14 `tests/unit/test_ci_stats.py` pass; 4/4 integration tests pass.
- `pnpm exec tsc --noEmit` clean.
- Trend classification uses strict `>=3` runs per half guard; rising and falling thresholds are symmetric at ±0.10.

## Deviations from spec

- None.
