# CI/CD flaky checks — make the card actionable

**Status:** Completed
**Priority:** Medium
**Type:** feature
**Apps:** devpulse
**Effort:** medium

## Overview

The "Flaky Checks" card on `/insights/cicd` (`backend/app/services/stats.py:3759-3827` →
`frontend/src/pages/insights/CIInsights.tsx:113-159`) lists check names with `>10%` failure
rate over `≥5` runs in the date window. In practice the rows are not actionable: a row like
`test-migrations (relay, sql_runner) — 100.0% — 6` tells you nothing about *which* PRs failed,
*who* owns the workflow, *when* it last ran, or whether the failure rate is rising or fading.
The only built-in next step is the `html_url` link to one example failure on GitHub.

This epic turns the card from a dashboard tile into a triage tool by making four targeted
improvements. Each is independently shippable and visible to the user.

## Why this matters

The card today conflates three very different problems behind one number:

1. **Truly broken checks** (≥90% fail) — abandoned jobs, removed workflows that still emit a
   failure status, matrix entries nobody owns. The right action is *delete or fix the
   workflow*, not "investigate flakiness".
2. **Truly flaky checks** (10–60% intermittent) — non-deterministic tests, infra hiccups.
   The right action is *look at the failing PRs to find the pattern*.
3. **Stale noise** — checks that haven't run in weeks because the workflow was renamed or
   removed; they linger in the date window because old PRs reference them. Today they
   pollute the list with no way to dismiss them.

The current card surfaces all three uniformly with no drill-in path. Splitting them and
adding a click-through PR list converts each row into a concrete next action.

## Phases

- [x] Phase 01: **Split broken vs flaky sections** → `01-split-broken-vs-flaky.md`
- [x] Phase 02: **Last-seen column + stale filter** → `02-last-seen-and-stale-filter.md`
- [x] Phase 03: **Trend direction indicator** → `03-trend-direction.md`
- [x] Phase 04: **Drill-down failing-PR list** → `04-drill-down-failing-prs.md`

## Dependency graph

```
01 ─┐
02 ─┤   (all four are independent — order is value/effort, not technical dependency)
03 ─┤
04 ─┘
```

Phases 01–03 are additive fields on `FlakyCheck` + `CIStatsResponse` plus same-page UI
changes. Phase 04 introduces a new endpoint (`GET /api/stats/ci/check/{name}/failures`) and
a new UI surface (modal or expanded row). Recommended ship order is 01 → 02 → 03 → 04 —
each fixes a real gap before the next one piles on, and 04 (the largest) benefits from the
noise reduction in 01+02.

## Out of scope

- **True flakiness via re-run detection** (compare `run_attempt > 1 AND conclusion ==
  success` on the same `head_sha`). That's the textbook flaky signal and a worthwhile
  follow-up, but it's a separate workstream and depends on us actually capturing
  `head_sha` + multiple attempts per check, which needs verification first. Not blocking
  this epic.
- **Workflow-file owner attribution** (CODEOWNERS lookup for `.github/workflows/*.yml`).
  Useful but adds dependency on `services/codeowners.py` (Phase 09 of `linear-insights-v2`)
  and a non-trivial path-mapping step. Defer until someone asks.
- **Renaming the card from "Flaky Checks"** — Phase 01 naturally retitles the sections
  ("Broken Checks" / "Flaky Checks") so the card header can stay generic ("CI Check
  Health") or split into two cards. Decide in Phase 01 implementation, no separate phase.

## Acceptance criteria for the epic

- A check at 100%/6 lands in a "Broken" section with a clear action prompt, not in
  "Flaky".
- A check that hasn't run in the last 7 days is hidden by default, with a toggle to
  show.
- Each row shows whether the failure rate is rising, falling, or stable across the window.
- Clicking a row reveals the list of PRs whose runs of this check failed, with author and
  date, so the user can ping someone or look at a real example without leaving the page.
