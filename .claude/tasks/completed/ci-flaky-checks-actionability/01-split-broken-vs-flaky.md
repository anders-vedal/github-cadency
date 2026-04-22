# Phase 01: Split broken vs flaky sections

**Status:** Completed
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** small
**Parent:** ci-flaky-checks-actionability/00-overview.md

## Scope

Today every check with `>10%` failure rate lands in one bucket called "Flaky". A 100%/6
check shows up alongside a 25%/40 check, even though the actions are very different:
the first is a *broken or abandoned* job (delete or fix the workflow), the second is a
*genuinely flaky* test (look at the failure pattern). Split them in the response and on
the page so the user knows what to do.

## Backend

- `backend/app/schemas/schemas.py` — add a `category: Literal["broken", "flaky"]` field
  to `FlakyCheck`.
- `backend/app/services/stats.py` (`get_ci_stats`, ~line 3815) — when building
  `flaky_checks`, set `category = "broken"` when `rate >= 0.9`, `"flaky"` otherwise. Keep
  the existing `>0.1` cutoff as the inclusion threshold (rows below 10% are still
  filtered out entirely).
- Sort within each bucket by `failure_rate desc` (already happens for the combined list —
  preserve after the categorization).

## Frontend

- `frontend/src/utils/types.ts` — add `category: 'broken' | 'flaky'` to the
  `FlakyCheck` type (whatever the local name is — match the schema).
- `frontend/src/pages/insights/CIInsights.tsx` — split the existing "Flaky Checks" card
  body into two sections rendered conditionally on count:
  - **Broken Checks** (`category === 'broken'`) — orange/red triangle icon, tooltip
    explaining "Failure rate ≥90% — these jobs are likely broken, abandoned, or have a
    workflow file that needs attention. Delete the job or fix it."
  - **Flaky Checks** (`category === 'flaky'`) — yellow/orange triangle, tooltip "Failure
    rate 10–90% — likely intermittent test failures. Click through to see which PRs."
  - If a section is empty, hide it entirely (don't show "No broken checks." noise).
  - If both are empty, fall back to the existing "No flaky checks detected" copy.
- The card header can stay "Flaky Checks" or become "CI Check Health" — pick whichever
  reads better once both sections are visible.

## Tests

- `backend/tests/...` — extend the existing CI stats test (find via grep:
  `get_ci_stats|test_ci_stats`) with two cases:
  - One check at 100%/10 → returns `category="broken"`
  - One check at 30%/20 → returns `category="flaky"`

## Acceptance

- A 100%/6 check appears under "Broken Checks", not under "Flaky Checks".
- A 25%/40 check appears under "Flaky Checks".
- Both sections render in the same card (or as two cards, builder's choice) with their
  own tooltip explaining what action to take.
- Existing API consumers don't break — `category` is additive.

## Blocked By

- None.

## Blocks

- None (Phase 02–04 are independent).

## Files Modified

- `backend/app/schemas/schemas.py` — added `category: Literal["broken", "flaky"] = "flaky"` to `FlakyCheck` (additive; default keeps old API consumers working).
- `backend/app/services/stats.py` — `get_ci_stats` sets `category="broken"` when `rate >= 0.9`, else `"flaky"`. Sort order unchanged (failure_rate desc naturally groups broken above flaky).
- `frontend/src/utils/types.ts` — added `category: 'broken' | 'flaky'` to the `FlakyCheck` interface.
- `frontend/src/pages/insights/CIInsights.tsx` — card retitled to "CI Check Health"; body now renders two conditional sections:
  - **Broken Checks** (red triangle, ≥90% tooltip) — only rendered when at least one row has `category === 'broken'`.
  - **Flaky Checks** (orange triangle, 10–90% tooltip) — only rendered when at least one row has `category === 'flaky'`.
  - When both are empty, falls back to the original "No flaky checks detected" copy.
- `backend/tests/unit/test_ci_stats.py` — 2 new tests (`test_broken_check_category` 100%/10 → broken, `test_flaky_check_category_midrange` 30%/20 → flaky); existing `test_flaky_check_detection` extended with a `category == "flaky"` assertion.

## Verification

- 11/11 `tests/unit/test_ci_stats.py` pass.
- 4/4 `tests/integration/test_ci_stats_api.py` pass (no changes, verifies additive field doesn't break API).
- `pnpm exec tsc --noEmit` clean.

## Deviations from spec

- None. Card header chosen: "CI Check Health" (spec left this as builder's choice).
