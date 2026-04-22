# Linear insights v2 — review follow-up fixes

**Status:** completed
**Priority:** High
**Type:** bugfix
**Apps:** devpulse
**Effort:** medium

## Overview

Post-ship review of the `linear-insights-v2` epic (completed 2026-04-22) surfaced a set of
correctness bugs, spec-compliance deviations, security gaps, missing test files, and
performance concerns. None are architectural — all are targeted fixes against already-shipped
surfaces. This epic closes that punch list.

Two characteristics of this work:
1. Several bugs silently produce wrong numbers in the UI (linkage rate, status-time p50/p90,
   DORA-v2 cohort metrics, rework rate). Fix priority is "fix the math first, write the
   missing regression tests alongside".
2. Phase 11 governance components (`DistributionStatCard`, `AiCohortBadge`,
   `StatCard.pairedOutcome`) shipped as dead code — implemented but unwired. Phase 05 below
   activates them on real stat cards so the governance work actually lands.

## Why this matters

The review surfaced that the shipped system displays mathematically-wrong numbers on at least
four surfaces (Linkage Quality page, Flow Analytics status distribution, DORA v2 main stat
cards, rework rate). None of the displayed numbers are extreme outliers that would jump out
to a reviewer, which is exactly why these bugs are dangerous — they pass plausibility checks
and get interpreted as fact. Additionally, the mandated test files for phases 04/05/06/07/11
were skipped, which is how at least three of the bugs reached production in the first place.

## Phases

- [x] Phase 01: **Analytics math bugs** → `01-analytics-math-bugs.md`
- [x] Phase 02: **DORA v2 cohort correctness** → `02-dora-v2-correctness.md`
- [x] Phase 03: **GitHub timeline sync reliability** → `03-timeline-sync-reliability.md`
- [x] Phase 04: **Frontend gating + spec-compliance wiring** → `04-frontend-gating-and-wiring.md`
- [x] Phase 05: **Governance components activation** → `05-governance-wiring.md`
- [x] Phase 06: **Security hardening** → `06-security-hardening.md`
- [x] Phase 07: **Missing test files** → `07-missing-test-files.md`
- [x] Phase 08: **Performance follow-ups** → `08-performance-followups.md`

## Dependency graph

```
01 ──┐
02 ──┼──> 07 (tests are written against the fixed behaviour)
03 ──┘

04 ── independent (frontend query gating + small backend deviations)
05 ── independent (governance wiring is additive)
06 ── independent (security hardening)
08 ── independent (performance-only, no behaviour change)
```

Phases 01, 02, 03, 04, 05, 06, 08 can run in parallel. Phase 07 should follow 01+02+03 so the
regression tests lock in the fixes rather than the pre-fix behaviour.

## Sequencing recommendation

1. Tranche A (correctness, can run concurrently): 01, 02, 03, 04
2. Tranche B (additive): 05, 06
3. Tranche C (after fixes land): 07
4. Tranche D (opportunistic): 08

## Acceptance criteria (epic-level)

- [x] All 10 ship-blocking correctness bugs from the review report fixed
- [x] Five missing test files created, each covering the regression behind a fixed bug
- [x] Phase 11 governance components wired into at least DORA and 2+ Insights pages
- [x] `ClassifierRule.pattern` validation hardened; ReDoS guard reused from `work_categories`
- [x] `MetricsUsageBanner` renders on every metric-surface route (Dashboard, Executive, Insights, Admin metrics pages)
- [x] `docs/metrics/catalog.md` generated from the `MetricSpec` registry
- [x] No backend test regressions; frontend type-check green

## Out of scope

- Rewriting `get_dora_metrics` v1 (v2 remains additive per original Phase 10 decision)
- Adding `MetricSpec` lint/CI enforcement (deferred — needs design for how to scope "metric-shaped" vs not)
- Adding `react-force-graph` for the review network (still table-of-clusters per original spec)
- Webhook-based Linear sync (original Phase 01 explicitly deferred this)

## References

- Review findings consolidated in the conversation that originated this epic (2026-04-22)
- Original epic: `.claude/tasks/linear-insights-v2/00-overview.md`
- Post-ship deviation log in the original overview's "Deviation follow-up" section
