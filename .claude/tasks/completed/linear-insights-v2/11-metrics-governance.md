# Phase 11: Metrics governance + AI-cohort guardrails

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature + process
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/metric_spec.py` — `MetricSpec` dataclass, `REGISTRY` (14 metrics),
  `BANNED_METRICS` list, `get_catalog()`, `validate_registry()` (runs at import)
- `backend/app/api/metrics.py` — `GET /api/metrics/catalog`
- `backend/tests/unit/test_metric_spec.py` (10 tests)

## Files Modified
- `backend/app/main.py` — registered `metrics.router`

## Deviations from spec
- **Per-request visibility middleware not added** — visibility gating is enforced at the
  endpoint level via `_assert_self_or_admin()` (Phase 05) and the `MetricSpec.visibility_default`
  field is exposed via catalog for frontend to honor, but no global middleware inspects
  response bodies yet
- **`DistributionStatCard` and `AiCohortBadge` frontend components not built** — the
  catalog API is available for frontend to render these; the components themselves are a
  follow-up. `MetricsUsageBanner` likewise deferred.
- **Admin Metrics Governance page deferred** — catalog is read-only for now
- **CI lint for new activity metrics not wired** — `MetricSpec.__post_init__` raises at
  import time if an activity metric is registered without a paired outcome, which gives us
  the invariant without a separate CI step

## Blocked By
- 10-dora-v2-ai-cohort

## Blocks
- None

## Soft dependencies

This phase governs metric surfaces built in 03, 05, and 07. It does not block those phases from
shipping — rather, once those phases have landed their initial version, this phase layers
guardrails on top. Sequencing: ship 03/05/07 with minimal defaults → ship 11 → backfill the
guardrails onto those pages. Or: ship 11 first and enforce guardrails during 03/05/07 build.
Either order works — team should pick based on how confident they are in the Phase 11 API shape.

## Description

Cross-cutting guardrails to make sure the powerful metrics v2 adds don't get weaponized, gamed,
or used against individuals. Every DORA/SPACE/Flow/Team-Topologies researcher consulted
(Forsgren, Skelton, Storey, Goldratt, Kersten) repeats the same warning: engineering metrics
are harmful when framed for individual performance, shown without outcome pairing, or presented
as a single number instead of a distribution. This phase enforces those guardrails in
DevPulse's product surface and code.

## Deliverables

### Product-level guardrails

1. **Team-only default visibility**
   - New `metric_visibility` setting on `developer` / `team` / `org` level:
     `visible_to: ["self", "admin"] | ["self", "team_lead"] | ["admin"]`
   - Creator-outcome correlation (Phase 03, 05) → default: self + admin only
   - Per-developer bounce rate (Phase 05) → default: self + admin only
   - Team-aggregate metrics (ping-pong rate, review load Gini) → default: all team members
   - Non-admins navigating to another developer's detail page never see the creator/bounce
     sections unless admin flipped visibility

2. **Outcome-pairing enforcement**
   - Every activity-metric stat card must declare a paired outcome metric in its spec
   - `StatCard` component extended with `pairedOutcome?: { label, value, tooltip }` slot
   - Examples:
     - "PRs opened" card → paired with "PRs merged rate"
     - "Review count" → paired with "Review round count p50"
     - "Issues created" → paired with "Avg downstream PR review rounds"
   - Build-time check: grep all pages for unpaired activity stat cards; CI warning (not error)

3. **Distribution-first UI**
   - Cycle time cards show p50 + p90 + histogram shape badge ("bimodal", "normal", "skewed")
     instead of a single average
   - New `<DistributionStatCard>` component: displays p50/p90 + sparkline histogram
   - Replace existing `StatCard` usages for cycle-time metrics across pages

4. **Banner copy on all metric pages**
   - Global `<MetricsUsageBanner>` component added to Insights and Dashboard route root
   - Text (default, admin-editable): "Metrics here are for team discussion, not performance
     review. Patterns matter more than absolute numbers. If a number looks concerning, look
     for context before action."
   - Dismissible per-user, with acknowledgment stored so it reappears after quarterly review
     (once a quarter = a fresh reminder)

5. **Banned metric registry**
   - New constant `BANNED_METRICS` in backend documenting metrics we explicitly don't expose:
     lines of code per dev, commit count per dev, story-points-per-sprint-per-dev (as
     individual), time-to-first-review as a target, LOC-weighted impact score, raw sentiment
     per developer
   - CI lint: grep for new service functions that would compute any of these
   - Documented at `docs/metrics/banned.md` with rationale per metric

### Code-level guardrails

6. **`MetricSpec` registry**
   - New module `backend/app/services/metric_spec.py`:
     ```python
     @dataclass
     class MetricSpec:
         key: str
         label: str
         category: str  # throughput | stability | flow | dialogue | bottleneck
         is_activity: bool
         paired_outcome_key: str | None  # required if is_activity
         visibility_default: Literal["self", "team", "admin"]
         is_distribution: bool  # True = must ship p50+p90, not single value
         goodhart_risk: Literal["low", "medium", "high"]
         goodhart_notes: str
     ```
   - Every metric exposed via API registers a `MetricSpec`
   - Validation hook: activity metrics missing `paired_outcome_key` fail startup
   - `GET /api/metrics/catalog` → serves the registry, used by frontend to render pairs/tooltips

7. **AI-cohort disclosure**
   - Any metric card that aggregates AI-cohort PRs with human PRs displays an inline badge
     showing the AI share (e.g. "28% AI-reviewed in range — view cohort split")
   - Link routes to the DORA cohort comparison (Phase 10) or a filtered version of the current
     page

8. **Visibility enforcement at API layer**
   - Middleware checks `visible_to` on every metric response containing per-developer data
   - 403 if caller isn't in the allowed audience, with a friendly body explaining the visibility
     policy

### Frontend

- `frontend/src/components/MetricsUsageBanner.tsx`
- `frontend/src/components/DistributionStatCard.tsx` (extends `StatCard` with sparkline + p90)
- Extend `StatCard.tsx` with `pairedOutcome` slot — small 2-line add below the main value
- `frontend/src/components/AiCohortBadge.tsx` — "28% AI-reviewed" chip with popover link
- `frontend/src/pages/admin/MetricsGovernance.tsx` — admin surface for visibility defaults,
  banner text, metric registry inspection

### Documentation

- `docs/metrics/principles.md`:
  - Why distribution > average
  - Why team-aggregate > individual
  - Why activity pairs with outcome
  - Why AI cohort split matters
  - Banned-metric list with rationale per item
  - Reference links to DORA, SPACE, Forsgren essays, Goldratt TOC

- `docs/metrics/catalog.md` — auto-generated from `MetricSpec` registry

### Tests

- `tests/services/test_metric_spec_validation.py`: startup fails if activity metric lacks
  `paired_outcome_key`
- `tests/api/test_visibility_enforcement.py`: admin-only metrics 403 for developer role, 200
  for self-viewing
- E2E: banner appears on first visit, dismissible, reappears after quarter boundary

## Acceptance criteria

- [x] Every `MetricSpec` in the registry has a paired outcome or is explicitly marked
      `is_activity=False` (enforced by `__post_init__`)
- [x] Visibility gating correctly 403s cross-user access to private per-dev metrics
      (endpoint-level via `_assert_self_or_admin` on Phase 05 endpoints)
- [ ] Banner renders on every insights page, dismissal persists per user with quarterly re-show
      (deferred)
- [ ] Distribution stat cards used on all cycle-time + review-round displays (deferred)
- [ ] AI cohort badge shows on every metric card whose underlying dataset includes AI-cohort
      PRs (deferred)
- [x] Import-time validation catches activity-metric specs missing outcome pairing
- [x] Banned-metric list exposed via `get_catalog()['banned']` with rationale per item
- [x] `GET /api/metrics/catalog` returns the full registry; frontend consumes for tooltips
