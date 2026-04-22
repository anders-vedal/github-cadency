# Metrics governance principles

DevPulse surfaces a lot of data about how engineering teams work. This document
captures the principles that shape what we measure, how we show it, and —
equally important — what we deliberately don't measure. The research base is
DORA (Forsgren et al.), SPACE (Storey et al.), Flow Framework (Kersten), Team
Topologies (Skelton), and Theory of Constraints (Goldratt), cross-referenced in
`08-research-synthesis.md` under `.claude/tasks/linear-insights-v2/`.

These principles are encoded in code via `backend/app/services/metric_spec.py`
(the `MetricSpec` registry + `BANNED_METRICS` list) and enforced at import time
so surfacing a new metric without pairing or visibility rules fails startup.

## 1. Distribution beats average

Cycle time, review rounds, time-in-state — none of these are normal
distributions. They're typically long-tailed with a fat right tail, and the
average misleads. A team whose cycle time distribution is bimodal ("fast bugs,
slow features") has very different problems from one whose distribution is
right-skewed ("mostly fine, a few stuck tickets"). An average smooths both into
the same number.

**How DevPulse applies this:**

- Every cycle-time metric ships `p50` and `p90`. The `MetricSpec.is_distribution`
  flag marks metrics that must be rendered with both percentiles.
- The `DistributionStatCard` component (Phase 11) renders p50 + p90 +
  sparkline histogram in place of a bare number.
- We never surface `avg_X` as a primary metric for bounded-distribution signals.
  Averages appear only as a secondary disclosure with sample size.

## 2. Team-aggregate beats per-individual

Per-developer metrics are weaponizable. A "bounce rate by author" leaderboard
creates incentives to avoid reviewing risky PRs, to batch commits, to pad LOC.
Team-aggregate metrics surface the same signal ("our review process is bouncy")
without attaching blame.

**How DevPulse applies this:**

- Default `MetricSpec.visibility_default` is `team`. A metric must explicitly
  opt into per-individual exposure.
- Creator-outcome metrics (downstream PR review rounds per ticket creator) are
  `visibility_default="self"` — visible to the developer themselves and admins,
  not peers. This is enforced at the API layer via
  `developers.py::_assert_self_or_admin`.
- Team Topologies auto-classification was deliberately skipped — too high
  misread risk. Team labels stay manual.

## 3. Activity metrics pair with outcome metrics

A metric like "PRs opened per week" tells you nothing about productivity. It
can go up because the team is unblocking faster (good), or because developers
are splitting PRs artificially to game throughput (bad). The same number, two
different stories.

**How DevPulse applies this:**

- Every `MetricSpec` with `is_activity=True` MUST declare a `paired_outcome_key`
  pointing to another metric. `MetricSpec.__post_init__` raises at import time
  if an activity metric ships without pairing.
- Examples in the registry:
  - `deployment_frequency` → paired with `change_failure_rate`
  - `wip_per_developer` → paired with `cycle_time_p50_s`
- Frontend `StatCard.pairedOutcome` slot renders the paired metric alongside
  the primary one.

## 4. AI-cohort transparency

AI-assisted code review and AI-authored PRs create a bimodal cycle-time
distribution. Blending the cohorts masks the real process health: fast AI-only
PRs flatter the average; slow human-only PRs with heavy review don't look as
bad relative to the blend. Each cohort also has different risk characteristics.

**How DevPulse applies this:**

- Phase 10 `services/ai_cohort.py` classifies every PR into
  `human` / `ai_reviewed` / `ai_authored` / `hybrid`.
- DORA v2 (`services/dora_v2.py`) provides per-cohort splits for all stability +
  throughput metrics.
- `AiCohortBadge` component (Phase 11) shows "X% AI-reviewed in range" on any
  card whose dataset mixes cohorts, with a link to the DORA v2 cohort
  comparison.
- The default AI-reviewer/author pattern lists are documented in
  `DEFAULT_AI_REVIEWER_USERNAMES`, `DEFAULT_AI_AUTHOR_LABELS`, and
  `DEFAULT_AI_AUTHOR_EMAIL_PATTERNS` at the top of `ai_cohort.py`. They're
  admin-overridable (once the CRUD surface lands).

## 5. Framing matters as much as math

A number like "bounces per review round" is statistically identical whether the
UI labels it "author performance score" or "pattern worth investigating". The
first framing invites blame; the second invites curiosity. Research shows the
frame determines whether a metric gets used for improvement or for surveillance.

**How DevPulse applies this:**

- `MetricsUsageBanner` (global, every insights page) repeats:
  *"Metrics here are for team discussion, not performance review. Patterns
  matter more than absolute numbers."*
- Creator-profile sections on Developer Detail are framed as "ticket clarity
  for self-reflection" with sample-size badges — never as a leaderboard.
- Tooltips on `goodhart_risk="high"` metrics include a one-line note about why
  optimizing the metric directly is dangerous. See `MetricSpec.goodhart_notes`.

## 6. Goodhart's law is real

*"When a measure becomes a target, it ceases to be a good measure."* The
metrics in the registry are diagnostic signals. The moment they become OKRs or
performance-review inputs, teams optimize the number rather than the outcome.

**How DevPulse applies this:**

- Every `MetricSpec` declares a `goodhart_risk: low | medium | high` and a
  `goodhart_notes` string. High-risk metrics ship with explicit guidance about
  failure modes (e.g. `review_round_count`: "Don't frame as author
  performance.")
- Explicitly banned metrics (see `banned.md`) are what happens when a common
  metric has already been weaponized across the industry and is not safe to
  surface even with guardrails.

## Maintenance

When you add a new metric to a surfaced API endpoint:

1. Register a `MetricSpec` in `backend/app/services/metric_spec.py`.
2. If it's an activity metric, supply `paired_outcome_key` — registry
   validation will fail startup otherwise.
3. If it's distribution-shaped, set `is_distribution=True` and use
   `DistributionStatCard` on the frontend.
4. Set `visibility_default` consciously — default to `team`, bump to `self` for
   per-individual exposure, `admin` only for sensitive rates.
5. Evaluate `goodhart_risk` honestly. If your answer is "high", either don't
   ship the metric, or ship it with a visible `goodhart_notes` disclaimer.
6. Update `banned.md` if an earlier draft of the metric didn't make the cut.

## References

- Forsgren, Humble, Kim — *Accelerate* (DORA methodology)
- Storey, Murphy-Hill et al. — *The SPACE of Developer Productivity* (2021)
- Kersten — *Project to Product* (Flow Framework)
- Skelton, Pais — *Team Topologies*
- Goldratt — *The Goal* (Theory of Constraints)
- 2024 DORA Report — revised band cut-points (used in `services/dora_v2.py`
  `BANDS_*` constants)
