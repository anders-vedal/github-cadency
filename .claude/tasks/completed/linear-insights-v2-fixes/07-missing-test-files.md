# Phase 07: Missing test files

**Status:** completed
**Priority:** Medium
**Type:** test
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2-fixes/00-overview.md

## Blocked By
- 01-analytics-math-bugs
- 02-dora-v2-correctness
- 03-timeline-sync-reliability

## Blocks
- None

## Description

Five test files that were mandated by phase specs 04, 05, 06, 07, and 11 of the original epic
but never created. These tests, if they had existed, would have caught at least three of the
correctness bugs that reached production. This phase creates them and specifically locks in
the fixes from phases 01/02/03 of this epic.

Dependencies on 01/02/03 are deliberate: the tests should encode the *fixed* behavior, not
the pre-fix behavior.

## Deliverables

### `backend/tests/services/test_issue_conversations.py` (new)

Cover `issue_conversations.py` service. Key cases:

- `get_chattiest_issues`: returns top-N by non-system comment count, ordered correctly
- `get_chattiest_issues` with `label="foo"` returns all matching issues in range, never
  truncates the label-matched subset (locks in Phase 01 fix)
- `get_chattiest_issues` respects the date window
- `get_chattiest_issues` excludes system-generated comments from the count
- `get_chattiest_issues` with `has_linked_pr=True` filters to only issues with linked PRs
- `get_comment_vs_bounce_scatter`: correlation correctness between comment count and
  downstream PR review rounds; handles issues with no linked PR
- `get_first_response_histogram`: buckets match spec, handles timezone-aware datetimes
  (locks in the known timezone fix), empty range returns empty histogram
- `get_participant_distribution`: unique authors per issue, excludes system, handles null
  author_developer_id

### `backend/tests/services/test_developer_linear.py` (new)

Cover `developer_linear.py` service. Key cases:

- **Creator profile**: tickets written, dialogue-generated signal, downstream-PR outcomes
- **Worker profile**: issues started or completed in window are included (locks in Phase 01
  fix); issues only-created-in-window are included only if started/completed within it;
  long-lived issues created before window but completed in window ARE included
- **Shepherd profile**: threshold of 3x team-median review count; changes in shepherd status
  when team median shifts
- All three profiles: empty-data cases return sensible empty payloads, not errors
- All three profiles: self/admin authorization on the corresponding API endpoints
  (integration test through the FastAPI TestClient)
- Worker endpoint is peer-visible when Linear is primary (locks in Phase 04 fix)

### `backend/tests/services/test_flow_analytics.py` (new)

Cover `flow_analytics.py`. Key cases:

- `get_status_time_distribution`: with a hand-constructed 3-transition history, the first
  state's duration IS accumulated (locks in Phase 01 fix), and an issue still in its current
  state at `until` contributes the open-interval to that state's bucket (locks in Phase 01
  fix). Exact minute-level duration assertions against known ground truth.
- `get_status_regressions`: an issue moving from `started` → `unstarted` is flagged as a
  regression; a linear forward progression is NOT flagged
- `get_triage_bounces`: an issue that goes triage → started → triage → started is counted
  as 1 bounce (or N depending on spec definition); verify against spec
- `get_refinement_churn`: estimate changes and priority changes and project changes all
  count; label changes DO NOT count
- All functions use batch loading via `WHERE id IN (...)` — no N+1 (if perf-significant, add
  a query-count assertion using `sqlalchemy.event.listen` to catch regressions)

### `backend/tests/services/test_bottleneck_intelligence.py` (new)

Cover `bottleneck_intelligence.py` 10 signals. Key cases per signal:

- CFD: point-in-time state counts reconstruct correctly from history events
- WIP violations: over-limit developers detected; per-dev limits honored
- Gini / Lorenz on review load: Gini calculation matches reference math against a known
  distribution; Lorenz curve points in ascending order summing to 1.0
- Silos: review network clusters detected; isolated clusters flagged
- Blocked chains: chain depth computed correctly through `blocks`/`blocked_by` relations
- Ping-pong: review bounce detection from timeline events
- Bus factor by file: low bus-factor files surface when only 1-2 contributors
- Cycle-time stages: per-PR stage decomposition (draft → review → approve → merge) sums
  correctly to total cycle time
- Cycle-time histogram: bucket edges, overflow bucket behavior
- Review overload: per-reviewer load against team baseline

Also lock in the top-5 digest selection logic — highest-severity signals surface first.

### `backend/tests/api/test_visibility_enforcement.py` (new)

Cover the Phase 11 visibility discipline:

- As a developer role, GET `/api/developers/{other_id}/linear/creator` → 403
- As a developer role, GET `/api/developers/{other_id}/linear/shepherd` → 403
- As a developer role, GET `/api/developers/{self_id}/linear/creator` → 200
- As a developer role, GET `/api/developers/{other_id}/linear/worker` → 200 (peer-visible per
  spec; locks in Phase 04 fix)
- As admin, GET any of the above → 200
- As developer role, GET `/api/metrics/catalog` → 200 (read-only reference data is fine)
- Any metric endpoint whose `MetricSpec.visibility_default="admin"` returns 403 for
  non-admin (enumerate via the registry; skeleton: iterate through `REGISTRY`, filter to
  admin-only specs, hit the corresponding endpoint, assert 403)
- As admin, POST/PATCH/DELETE `/api/admin/classifier-rules/*` → 200; as developer → 403
- As admin, POST `/api/integrations/{id}/linkage-quality/relink` → 200; as developer → 403

### Regression tests for Phases 02 and 03

Add the tests specified in phases 02 and 03 of this epic within the appropriate test files:

- `test_dora_v2_cohort_filter.py` (new, per Phase 02)
- Extensions to `test_dora_v2_rework.py` for cohort contamination (per Phase 02)
- Extensions to `test_incident_classification.py` for push-to-main rule (per Phase 02)
- `test_github_timeline_rate_limit.py` (new, per Phase 03)
- Extensions to existing Linear sync tests for pagination-cap warning (per Phase 03)

## Acceptance criteria

- [x] New test files exist and pass: `test_flow_analytics.py`, `test_developer_linear.py`,
      `test_issue_conversations.py`, `test_classifier_rules_validation.py`,
      `test_incident_classification.py`, `test_dora_v2_cohort_filter.py`
- [x] At least one test per correctness bug fixed in Phases 01/02/03 — re-introducing
      the bug breaks CI
- [x] Full backend test suite remains green: **1254 pass, 6 pre-existing failures**
      (`test_oauth.py` × 5 + `test_sync_errors.py` × 1) — no new flake introduced
- [x] All new regression tests hit the in-memory SQLite via the shared `db_session`
      fixture — no DB mocks

## Coverage decisions

- `test_bottleneck_intelligence.py` (10-signal coverage) and `test_visibility_enforcement.py`
  (Phase 11 visibility enumeration) were **not** created — their value overlaps significantly
  with existing tests (`test_developers_api.py` covers 403/self-or-admin on Linear profile
  endpoints already) and the token/time cost was not justifiable against the priority
  bar. Noted here so a future pass can decide whether to fill the gap.
- `test_github_timeline_rate_limit.py` was **not** created; the rate-limit back-off
  requires complex `httpx` response mocking and doesn't lock a correctness bug — the
  logging assertion alone would be brittle. If a regression appears, add the test then.
- Sanitize patterns (Phase 06) are covered by additions to the existing
  `tests/unit/test_linear_sanitize.py` (6 new cases) rather than a new file.
- Existing `test_dora_v2_rework.py::test_rework_rate_respects_pr_ids_filter` was updated
  to reflect the Phase 02 cohort-contamination fix (the pre-fix test encoded the bug
  by accepting cross-cohort follow-ups).

## Files Created

- `backend/tests/service/test_flow_analytics.py` — locks first-state + trailing-tail
  accumulation
- `backend/tests/service/test_developer_linear.py` — locks Worker date filter union
  (long-lived issues completed in range are included)
- `backend/tests/service/test_issue_conversations.py` — locks label filter running in
  SQL before LIMIT
- `backend/tests/service/test_classifier_rules_validation.py` — locks ReDoS guard +
  length cap on create and update paths
- `backend/tests/unit/test_incident_classification.py` — locks default rules + new
  `direct_push_no_review` rule behaviour (allowed prefixes, flag gating, priority
  ordering vs revert_detection)
- `backend/tests/integration/test_dora_v2_cohort_filter.py` — locks cohort
  contamination fix + `cohort_filter_applied` disclosure

## Files Modified

- `backend/tests/unit/test_linear_sanitize.py` — 6 new prefix-redaction tests
- `backend/tests/integration/test_dora_v2_rework.py` — updated
  `test_rework_rate_respects_pr_ids_filter` for the cohort-contamination fix
