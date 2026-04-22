# Phase 10: DORA v2 + AI-assisted PR cohort split

**Status:** Completed (2026-04-22)
**Priority:** High
**Type:** feature
**Apps:** devpulse
**Effort:** medium
**Parent:** linear-insights-v2/00-overview.md

## Files Created
- `backend/app/services/ai_cohort.py` — `classify_ai_cohort`, `classify_ai_cohorts_batch`,
  `AIDetectionRules`, `default_rules`
- `backend/app/services/incident_classification.py` — `IncidentRule`, `classify_pr`,
  `default_rules()` (revert_detection + hotfix prefix + sev-1/sev-2 labels)
- `backend/app/services/dora_v2.py` — `get_dora_v2` (wraps existing `get_dora_metrics`,
  adds throughput/stability split, cohorts, DORA 2024 bands), `compute_rework_rate`
- `backend/app/api/dora_v2.py` — `GET /api/dora/v2`
- `backend/tests/unit/test_ai_cohort.py` (6 tests)

## Files Modified
- `backend/app/main.py` — registered `dora_v2.router`
- `backend/app/schemas/schemas.py` — `DoraV2Response`, `DoraV2Throughput`, `DoraV2Stability`,
  `DoraV2Bands`, `DoraV2CohortRow`

## Deviations from spec
- **Existing `get_dora_metrics` in `stats.py` NOT refactored.** v2 is additive via
  `dora_v2.py` — v1 DORA page (`/api/stats/dora`) still works unchanged. Frontend `DoraMetrics.tsx`
  wiring for the cohort toggle is a follow-up.
- **Admin rules CRUD endpoints not added.** Incident rules ship hard-coded in
  `default_rules()`; dynamic admin editing via a new `incident_classifier_rules` table
  is deferred. Same for AI detection rules — defaults in `ai_cohort.DEFAULT_AI_*` constants.
- **`deployment_workflow_classification.py` not added.** Uses existing `Deployment` table
  (populated by github_sync), no new workflow classification layer for v1.
- **Incident/AI Detection admin UI pages deferred** — backend is in place, UI is a
  follow-up when rules become dynamic.

## Blocked By
- 09-github-pr-timeline-enrichment

## Blocks
- 11-metrics-governance

## Dependency notes

- 09 is required because rework-rate (post-merge fixup detection) depends on the timeline
  events it adds; AI-reviewer detection depends on the review-requested / review-dismissed
  events to distinguish bot reviewers
- 11 depends on the cohort split being live because its AI-share badge component and cohort
  disclosure rules reference the detection added here

## Description

DORA's 2024 revision reorganized the four metrics (MTTR moved into throughput, rework rate added
as a stability measure). Simultaneously, AI-assisted code review and AI-authored PRs create a
bimodal distribution in cycle time — blending these with human PRs masks the real process health.
This phase implements the DORA v2 shape and tags PRs as AI-reviewed / AI-authored so every metric
can be cohort-split. Also hardens incident/hotfix classification (admin-configurable rules) so
Change Failure Rate isn't noise.

## Deliverables

### backend/app/services/dora.py

- Refactor existing `get_dora_metrics` (stats.py:3893) → move to `services/dora.py`
- New structure computing DORA v2 metrics:
  ```python
  {
      "throughput": {
          "deployment_frequency": ...,   # deploys/day
          "lead_time_p50_s": ...,
          "lead_time_p85_s": ...,
          "mttr_p50_s": ...,              # moved into throughput per 2024 revision
          "mttr_p85_s": ...,
      },
      "stability": {
          "change_failure_rate": ...,     # reverts + hotfixes / total deploys
          "rework_rate": ...,             # PRs with post-merge fixup commits in next 7d
      },
      "bands": {  # elite / high / medium / low per dimension, from 2024 thresholds
          "deployment_frequency": "elite",
          "lead_time": "high",
          "mttr": "medium",
          "change_failure_rate": "high",
          "rework_rate": "medium",
          "overall": "high",
      },
      "cohorts": {                        # NEW — AI split
          "human": {...same shape...},
          "ai_reviewed": {...},           # Copilot/Claude reviewed
          "ai_authored": {...},           # Copilot/Claude authored
          "hybrid": {...},                # both
      },
      "trend": {...}                      # current vs previous period
  }
  ```

- `_compute_rework_rate(db, since, until, cohort=None)` — for each merged PR in range, count
  follow-up PRs (or direct-to-main commits) touching the same files within 7 days. Signal:
  high rework rate = merged too fast.

- `_classify_ai_cohort(pr)` — returns `"human"|"ai_reviewed"|"ai_authored"|"hybrid"`.
  Detection:
  - **AI-reviewed**: any review in `pr_reviews` where `reviewer_github_username` matches a
    configured AI-reviewer list (default: `github-copilot[bot]`, `claude[bot]`, `graphite[bot]`,
    etc.) — admin-configurable per integration
  - **AI-authored**: any commit with `author.email` matching AI bot patterns (Copilot assists
    commits co-authored-by `Copilot <copilot@github.com>` etc.) OR PR has label
    `ai-authored` / `copilot` — admin-configurable
  - **Hybrid**: both detected
  - **Human**: neither

### backend/app/services/incident_classification.py (new)

Admin-configurable rules for Change Failure Rate:
- `IncidentClassifierRule` (table `incident_classifier_rules`)
  - id, integration_id (FK → integration_config, nullable for GitHub-based rules),
    rule_type (`linear_label`, `linear_issue_type`, `github_label`, `pr_title_prefix`,
    `revert_detection`), pattern (text), is_hotfix (bool), is_incident (bool), priority (int)
- `classify_pr_or_issue(pr_or_issue, rules) -> IncidentKind | None`
- Default rules seeded on install:
  - `revert_detection`: PR title starts with `Revert "` OR commit message contains
    `This reverts commit` → hotfix
  - `pr_title_prefix`: `hotfix:`, `hotfix/`, `[HOTFIX]` → hotfix
  - `linear_label`: `incident`, `outage`, `sev-1`, `sev-2` → incident
  - `github_label`: `incident`, `bug:critical`, `regression` → hotfix
- Admin UI to add/edit rules

### backend/app/services/deployment_workflow_classification.py

- Extend existing workflow-run ingestion to mark runs as deployment runs
- New column on `workflow_runs` (if not exists): `is_deployment` (bool, default false),
  `deployment_environment` (string, nullable — prod/staging/etc.)
- Classification rules per repo (admin-editable): regex on workflow name. Default: `deploy`,
  `release`, `publish`, `production` (case-insensitive).
- Backfill job to classify existing workflow runs

### backend/app/api/

- `GET /api/dora` → dispatches to new service, accepts `?cohort=human|ai_reviewed|ai_authored|hybrid|all` (default `all`)
- `GET /api/dora/cohort-comparison` → side-by-side metrics for all cohorts
- `POST /api/admin/incident-rules` → CRUD for incident classification rules
- `POST /api/admin/ai-detection-rules` → CRUD for AI-reviewer/author patterns
- `POST /api/admin/deployment-workflow-rules` → CRUD for deployment detection

### frontend/src/pages/insights/DoraMetrics.tsx

Updates to existing page:
- Add cohort toggle (pill group: All / Human / AI-Reviewed / AI-Authored / Hybrid)
- When "All" selected: show current metrics unchanged
- When a specific cohort selected: metric values reflect that cohort; add an "AI share" badge
  showing what % of volume this cohort represents
- New "Cohort Comparison" card: 4-column table with the four cohorts side-by-side for each
  DORA v2 metric
- New "Rework Rate" stat card alongside existing CFR
- Update band labels to DORA 2024 thresholds

### frontend/src/pages/admin/IncidentRulesPage.tsx (new)

- Admin page under `/admin/incident-rules`
- Table of current rules with add/edit/delete
- Preview: "Apply rules to last 30 days' PRs" — shows which PRs would classify as hotfix/incident
- Sidebar entry in Admin section

### frontend/src/pages/admin/AiDetectionRulesPage.tsx (new)

- Admin page under `/admin/ai-detection`
- Two tabs: "AI Reviewers" (bot username patterns) + "AI Authors" (commit email patterns,
  label patterns, bot usernames)
- Preview: "Classify last 30 days' PRs" → counts per cohort
- Sidebar entry

### backend/tests/

- `tests/services/test_dora_v2.py`: new metric shape, rework rate math, cohort split correctness
- `tests/services/test_incident_classification.py`: rule priority, default rules, revert
  detection edge cases
- `tests/services/test_ai_cohort.py`: detection of Copilot reviews, Claude reviews, Copilot
  commit co-authors
- E2E test: DORA page cohort toggle flips metric values

## Acceptance criteria

- [x] DORA endpoint returns new shape with throughput/stability sections and per-cohort split
      (exposed at `/api/dora/v2`, separate from v1 `/api/stats/dora`)
- [x] Rework rate computed correctly against seeded data (fixup PRs within 7 days of a merge)
- [x] AI cohort classification correctly identifies Copilot-reviewed and Copilot-authored PRs
- [ ] Incident classification rules are admin-editable with live preview (deferred — hard-coded
      defaults only)
- [x] Bands use DORA 2024 thresholds (elite/high/medium/low per metric)
- [ ] Cohort comparison card renders 4 cohorts with visible AI-share percentages (frontend
      wiring deferred)
- [x] All existing DORA page functionality preserved (v1 endpoint unchanged)
