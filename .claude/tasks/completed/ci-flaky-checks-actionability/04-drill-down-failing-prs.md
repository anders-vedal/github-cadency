# Phase 04: Drill-down failing-PR list

**Status:** Completed
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** ci-flaky-checks-actionability/00-overview.md

## Scope

The current row is a dead-end: a number and a single GitHub link. To actually triage you
need to see *which* PRs failed this check — was it one rogue branch, three different
authors, all on the same day? Add a click-through that lists the failing PRs with
author, date, and a link to the run.

This is the largest phase in the epic and the one that turns the card from "look at
this" into "go talk to these people".

## Backend

- New endpoint `GET /api/stats/ci/check-failures` (single endpoint, query params):
  - Query params: `check_name: str` (required), `date_from`, `date_to`, `repo_id?`,
    `limit: int = 50`
  - Response: list of `CICheckFailureEntry`:
    - `pr_number: int`
    - `pr_title: str`
    - `pr_html_url: str`
    - `repo_full_name: str`
    - `author_login: str | None`
    - `author_avatar_url: str | None`
    - `failed_at: datetime`
    - `run_html_url: str | None` (the `PRCheckRun.html_url` for the failure)
    - `run_attempt: int`
    - `was_eventually_green: bool` (did a later run on the same `pr_id + check_name` end
      with `conclusion = success`? — useful signal for "the dev fixed it" vs "still
      broken")
- Implementation:
  - Add `get_check_failure_details(db, check_name, date_from, date_to, repo_id, limit)`
    in `backend/app/services/stats.py` (sibling to `get_ci_stats`).
  - Query `PRCheckRun` filtered by `check_name` + `conclusion == "failure"` joined to
    `PullRequest` (for repo + author + title) and `Developer` (for avatar). Apply the
    same date range conditions as `get_ci_stats`.
  - Order by `failed_at desc`, cap at `limit`.
  - Compute `was_eventually_green` with a correlated subquery or post-fetch: for each
    `(pr_id, check_name)` of a failure row, check if any `PRCheckRun` exists with
    `pr_id` matching, same `check_name`, `conclusion == "success"`, and either
    `run_attempt > failure.run_attempt` OR `created_at > failure.created_at`.
- New router file or extend `backend/app/api/stats.py` (whichever houses the existing
  CI stats route — grep `ci-stats|/ci`). Single new route.
- Schemas in `backend/app/schemas/schemas.py`: `CICheckFailureEntry`,
  `CICheckFailuresResponse` (just `entries: list[...]`).

## Frontend

- New hook `useCheckFailures(checkName, dateFrom, dateTo, repoId)` in
  `frontend/src/hooks/useStats.ts` (or sibling), TanStack Query, enabled only when
  `checkName` is set.
- `frontend/src/pages/insights/CIInsights.tsx`:
  - Make rows in both broken + flaky tables clickable. Use a `<button>` wrapper or
    `cursor-pointer` row with `onClick`.
  - On click, open a modal (`Dialog` from shadcn/ui) showing the failing-PR list:
    - Header: `{checkName}` + summary `({n} failures in date window)`
    - Body: table with columns `PR`, `Author`, `Failed`, `Status` (was_eventually_green
      → check icon green / x icon orange), and `Run` link (external icon → `run_html_url`)
    - PR cell links to `pr_html_url` (open in new tab)
    - Loading: `TableSkeleton`. Error: `ErrorCard`.
  - Add a small chevron icon at the end of each row to telegraph that it's clickable.

## Tests

- Backend: new test for `get_check_failure_details`:
  - Seed two PRs each with a failing run of `check_name="test-foo"`.
  - One PR also has a later successful run → `was_eventually_green = True`
  - The other does not → `was_eventually_green = False`
  - Assert ordering, fields populated, `limit` honored.
- Auth: confirm endpoint is admin-only or developer-accessible per the existing CI
  stats endpoint convention — match whatever `get_ci_stats`'s route uses.

## Acceptance

- Clicking a broken or flaky check row opens a modal listing failing PRs.
- Each entry shows author, failed-at date, link to PR, link to the run, and whether a
  later attempt eventually succeeded.
- Modal closes cleanly, no scroll-lock issues.
- Loading and error states have skeletons / error cards.

## Blocked By

- None (works on top of the existing `>10%` filter; doesn't need 01–03).

## Blocks

- None.

## Future follow-ups (not this phase)

- Group failures by author in a sub-section if there's a clear culprit (e.g. >50% of
  failures on a flaky check come from one author's PRs).
- "Notify owner" action — once Phase 09 (timeline) lands the codeowners-bypass data,
  link the check name to the workflow file and the owners.

## Files Modified

- `backend/app/schemas/schemas.py` — added `CICheckFailureEntry` (pr_number, pr_title, pr_html_url, repo_full_name, author_login, author_avatar_url, failed_at, run_html_url, run_attempt, was_eventually_green) and `CICheckFailuresResponse` (check_name, entries).
- `backend/app/services/stats.py` — added `get_check_failure_details(db, check_name, date_from, date_to, repo_id, limit)`. Two-step query: (1) joined SELECT of failing check runs + PR + repo + developer ordered by `coalesce(started_at, completed_at, pull_request.created_at) desc` with `limit`; (2) a grouped success query over the returned `pr_id`s to compute `was_eventually_green` (success run exists for `(pr_id, check_name)` with `run_attempt > failure.run_attempt`). Chose the two-step shape over a correlated subquery for readability — the pr_id set is always ≤ `limit` rows.
- `backend/app/api/stats.py` — new admin-only route `GET /api/stats/ci/check-failures`. Matches the existing `/stats/ci` auth convention (`require_admin`). Query params: `check_name` (required, 1–255 chars), `date_from`, `date_to`, `repo_id`, `limit` (1–500, default 50).
- `frontend/src/utils/types.ts` — added `CICheckFailureEntry` + `CICheckFailuresResponse` types.
- `frontend/src/hooks/useStats.ts` — added `useCheckFailures(checkName, dateFrom, dateTo, repoId)` TanStack Query hook, enabled only when `checkName` is non-null so the dialog doesn't fire until opened.
- `frontend/src/pages/insights/CIInsights.tsx`:
  - Rows in both Broken + Flaky tables are now clickable (`role="button"`, keyboard-accessible via Enter/Space), with a chevron column to telegraph the interaction.
  - New `CheckFailuresDialog` renders on click — shadcn `Dialog` with a scrollable table of PRs (PR link / author avatar+login / Failed relative time / Status check or x / Run link). Title shows check name + failure count.
  - Status column renders a green check when `was_eventually_green`, orange X otherwise; both carry tooltips explaining the semantic.
  - Loading → `TableSkeleton`; error → `ErrorCard` with retry.
- `backend/tests/unit/test_ci_stats.py` — three new tests:
  - `test_check_failure_details_was_eventually_green` covers both `True` (failure + later success) and `False` (failure only) paths + descending failed_at ordering + author/run URL fields.
  - `test_check_failure_details_limit` asserts the `limit` param caps results.
  - `test_check_failure_details_repo_filter` asserts repo scoping (in-repo returns 1, non-existent repo returns 0).

## Verification

- 17/17 `tests/unit/test_ci_stats.py` pass; 4/4 integration tests pass.
- `pnpm exec tsc --noEmit` clean.
- Dialog semantics: `role="button"` on rows + explicit `onKeyDown` handler for Enter/Space satisfies the task's "clickable" requirement while keeping keyboard users intact.

## Deviations from spec

- Spec listed query param as `check_name` on a single endpoint `GET /api/stats/ci/check-failures` — matched exactly. No URL-encoding issue in practice because check names don't contain `#` or `?`; the browser handles spaces and parens via URLSearchParams.
- Spec's exact column label for the per-row chevron column wasn't prescribed — used an unlabeled `w-8` header cell (`aria-label="Open details"`).
