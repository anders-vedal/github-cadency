# Phase 02: DORA v2 cohort correctness

**Status:** completed
**Priority:** High
**Type:** bugfix
**Apps:** devpulse
**Effort:** small
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- None

## Blocks
- 07-missing-test-files

## Description

Three bugs in the DORA v2 + AI-cohort layer (Phase 10 of the original epic) that mean the
displayed numbers on `/insights/dora` are wrong when a cohort is selected. Plus one missing
default rule that under-reports incidents on repos with direct-push hotfixes.

## Deliverables

### `backend/app/services/dora_v2.py` — propagate cohort filter to baseline metrics

**Bug** (lines 169-172): when `cohort != "all"` is passed, `get_dora_v2` still calls
`get_dora_metrics` with the full dataset. The `throughput`, `stability`, and DORA-2024 `bands`
sections always reflect all PRs. Only the `cohorts` sub-dict honors the filter.

The frontend `DoraMetrics.tsx` lets the user pick a cohort, then displays stat cards driven
by these top-level fields. The stat cards silently display all-cohort numbers regardless of
the picker state. This is a correctness issue — reviewing engineers believe they are looking
at AI-reviewed PR metrics when they are looking at the full dataset.

**Fix**:
1. When `cohort != "all"`, filter the PR set by cohort before passing to `get_dora_metrics`.
   Easiest path: classify PRs once into cohort buckets, pick the target bucket, compute
   metrics on that slice only. Reuse the existing cohort classifier from `ai_cohort.py`.
2. The `cohorts` sub-dict continues to show all four cohorts for comparison regardless of the
   top-level filter.
3. If computing the cohort-filtered baseline metrics is expensive (N queries), cache the
   classifier result per-request and reuse.

### `backend/app/services/dora_v2.py` — `compute_rework_rate` cohort contamination

**Bug** (lines 119-143, 226-227): the self-join that finds follow-up PRs touching the same
files applies `base_pr.id.in_(pr_ids)` but not `followup_pr.id.in_(pr_ids)`. When called
per-cohort, follow-ups from OTHER cohorts count as rework against the current cohort's base
PRs. Example: an AI-authored follow-up PR touching `package.json` within 7 days of a human PR
counts as rework against the human cohort.

**Fix**: when `pr_ids` is provided, apply the same filter to the followup side:
```python
if pr_ids:
    query = query.where(
        base_pr.id.in_(pr_ids),
        followup_pr.id.in_(pr_ids),
    )
```

Keep the existing behavior for the unfiltered/all-cohort case (both sides unconstrained — all
merged PRs in range).

### `backend/app/services/incident_classification.py` — add `push-to-main without review` rule

**Gap** (lines 52-124): spec lists "push-to-main without review" as a default incident signal.
`default_rules()` covers revert, hotfix prefixes, and labels only. Change Failure Rate
under-counts on repos with direct-push hotfix culture.

**Fix**: add a rule entry that matches commits pushed directly to the default branch (no PR
wrapper) where there is no associated review. DevPulse's models have `PullRequest` rows for
PRs; direct pushes live in the commit stream with no linked PR. The rule implementation:

1. Identify commits on the default branch whose SHA does NOT appear in any merged PR's
   `merge_commit_sha` or `commits` list for a 24-hour window post-commit.
2. Treat such commits as incident candidates if the commit message does not start with an
   allowed prefix (feat/docs/chore/etc — configurable).

Keep this as a default rule in `default_rules()`; admins can disable via the Phase 10
classifier-rules admin page (already exists).

Consider: if the computation adds cost to every DORA v2 request, precompute the flag on
commits at sync time and store in a column, or cache per-request. Default to simplest path
first, optimize if profiling shows it matters.

## Testing

- `backend/tests/integration/test_dora_v2_cohort_filter.py`: seed PRs in multiple cohorts,
  call `get_dora_v2(cohort="human")`, assert `throughput.merged_prs` reflects only human PRs
  (not the total).
- Extend `test_dora_v2_rework.py` (already exists) with a multi-cohort scenario: base human
  PR, follow-up AI-authored PR on same file within 7 days. Assert `compute_rework_rate` for
  cohort=human does NOT count the AI follow-up.
- `test_incident_classification.py`: add test that a direct-push commit with no linked PR and
  generic message classifies as incident.

## Acceptance criteria

- [x] `GET /api/dora/v2?cohort=human` returns `stability.rework_rate` computed on the
      human cohort only; the `cohorts` sub-dict shows all four cohorts. Deployment-based
      metrics (`throughput`, `change_failure_rate`, `mttr`) stay unchanged and are flagged
      via `cohort_filter_applied` in the response — Deployments carry no cohort signal
      so honest disclosure beats silent miscounting.
- [x] `compute_rework_rate(pr_ids=cohort_pr_ids)` only counts follow-ups that are also in
      `pr_ids` — no cross-cohort contamination
- [x] `classify_pr` returns `incident=True` for direct-push commits to main with no review
      and no allowed message prefix
- [x] Regression tests above pass and cover all three fixes

## Implementation notes

- `get_dora_v2` now classifies PRs into cohort buckets up-front and reuses the same map
  for both the top-level `rework_rate` filter and the `cohorts` breakdown, so cohort
  classification runs exactly once per request.
- Response gains a `cohort_filter_applied` object: boolean per top-level metric key so
  the UI can badge Deployment-based numbers as "all PRs" rather than silently matching
  the cohort picker.
- `classify_pr` takes a new `is_direct_push_to_main: bool = False` parameter; a new
  `direct_push_no_review` rule type (priority 50) fires when the flag is set and the
  commit subject doesn't start with any `DEFAULT_ALLOWED_DIRECT_PUSH_PREFIXES`
  (feat/fix/docs/chore/refactor/test/style/ci/build/perf/revert). Admins can override
  the allowlist by creating a `direct_push_no_review` rule with a comma-separated
  `pattern`.

## Files Modified

- `backend/app/services/dora_v2.py`
- `backend/app/services/incident_classification.py`
- `backend/app/services/classifier_rules.py` (whitelists `direct_push_no_review`)
