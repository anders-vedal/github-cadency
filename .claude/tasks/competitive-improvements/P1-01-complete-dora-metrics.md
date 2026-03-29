# P1-01: Complete DORA Metrics (4/4)

> Priority: 1 (Table Stakes) | Effort: Medium | Impact: High
> Competitive gap: All major competitors offer all 4 DORA metrics. DevPulse only has 2/4.

## Context

DevPulse currently implements **Deployment Frequency** and **Lead Time for Changes** via the `deployments` table and `get_dora_metrics()` in `backend/app/services/stats.py`. Missing: **Change Failure Rate (CFR)** and **Mean Time to Recovery (MTTR)**.

Gartner considers DORA 4/4 table stakes for engineering intelligence platforms. Every competitor (LinearB, Jellyfish, Swarmia, DX, Sleuth) offers all four.

## What to Build

### Change Failure Rate (CFR)

**Definition:** Percentage of deployments that cause a production failure (rollback, hotfix, or incident).

**Implementation approach — GitHub-native signals (no external incident tracker):**

1. **Detect failure deployments** by correlating:
   - Revert PRs merged shortly after a deployment (revert detection already exists in `pull_requests.is_revert`)
   - Failed deployment workflow runs following a successful one (status = "failure" after "success" on same environment)
   - Hotfix PRs: PRs merged to default branch with labels like `hotfix`, `urgent`, `incident`, or branch names matching `hotfix/*`

2. **New fields on `deployments` table:**
   - `is_failure: bool = False` — flagged if followed by revert/hotfix/failed deploy
   - `failure_detected_via: str | None` — "revert_pr", "failed_deploy", "hotfix_pr"
   - `recovered_at: datetime | None` — timestamp of the recovery deployment
   - `recovery_deployment_id: int | None` — FK to the deployment that fixed this one

3. **Computation:**
   ```
   CFR = count(deployments where is_failure=True) / count(all deployments) * 100
   ```

4. **DORA bands for CFR:**
   - Elite: 0-5%
   - High: 5-10%
   - Medium: 10-15%
   - Low: >15%

### Mean Time to Recovery (MTTR)

**Definition:** Average time between a failure deployment and its recovery deployment.

**Implementation approach:**

1. **Link failure → recovery:** When a revert PR merges or a new successful deployment follows a failed one, compute `recovery_time_s = recovered_at - deployed_at`
2. **New field on `deployments`:** `recovery_time_s: int | None`
3. **Computation:**
   ```
   MTTR = avg(recovery_time_s) for all failure deployments with recovery in period
   ```

4. **DORA bands for MTTR:**
   - Elite: <1 hour
   - High: 1-24 hours
   - Medium: 24-168 hours (1 week)
   - Low: >168 hours

## Backend Changes

### Models (`backend/app/models/models.py`)
- Add to `Deployment`: `is_failure`, `failure_detected_via`, `recovered_at`, `recovery_deployment_id`, `recovery_time_s`

### Schemas (`backend/app/schemas/schemas.py`)
- Extend `DORAMetricsResponse` with:
  - `change_failure_rate: float | None`
  - `cfr_band: str`
  - `avg_mttr_hours: float | None`
  - `mttr_band: str`
  - `failure_deployments: int`
- Extend `DeploymentDetail` with failure fields

### Service (`backend/app/services/stats.py`)
- Add `_cfr_band()` and `_mttr_band()` classification functions
- Extend `get_dora_metrics()` to compute CFR and MTTR
- Add DORA overall rating (composite of all 4 metrics)

### Sync (`backend/app/services/github_sync.py`)
- After `sync_deployments()`, add `detect_deployment_failures()`:
  1. For each successful deployment, check if a revert PR was merged within 48h pointing at the deployed SHA
  2. Check if the next deployment on the same repo failed
  3. For each failure, find the next successful deployment as recovery
  4. Compute `recovery_time_s`

### Migration
- Alembic migration adding new columns to `deployments`

## Frontend Changes

### DORA Metrics Page (`frontend/src/pages/insights/DoraMetrics.tsx`)
- Add CFR and MTTR cards alongside existing Deployment Frequency and Lead Time
- Add DORA summary card showing overall DORA performance level
- Add failure timeline visualization (mark failures on deployment timeline)
- Show CFR trend over time

### Types (`frontend/src/utils/types.ts`)
- Extend `DORAMetricsResponse` interface with new fields

## Testing
- Unit test `detect_deployment_failures()` with mock deployment + revert PR scenarios
- Unit test CFR/MTTR band classification
- Unit test the composite DORA rating logic
- Test edge cases: no deployments, no failures, recovery without matching failure

## Status

**Completed** — 2026-03-29

## Acceptance Criteria
- [x] CFR computed from revert PRs + failed deploys + hotfix PRs
- [x] MTTR computed from failure→recovery deployment pairs
- [x] DORA bands for both new metrics match industry standard thresholds (DORA research: CFR elite <5%, high <15%, medium <45%, low >=45%)
- [x] Overall DORA performance level (Elite/High/Medium/Low) shown — uses lowest-of-all-four logic
- [x] Frontend shows all 4 DORA metrics with deployment timeline chart
- [x] Works without external incident tracker (pure GitHub signals)

## Deviations from Spec
- CFR band thresholds use DORA research values (elite <5%, high <15%, medium <45%) instead of spec's tighter values (0-5%, 5-10%, 10-15%), per user decision
- Hotfix detection is configurable via `HOTFIX_LABELS` and `HOTFIX_BRANCH_PREFIXES` env vars instead of hardcoded, per user decision
- Deployment timeline uses a scatter chart (success/failure dots over time) instead of a bar-based visualization
- "Frontend shows all 4 DORA metrics with trends" — shows 6 stat cards + 5 band indicators + deployment timeline. No time-series trend chart per metric (would require additional API endpoint for per-period breakdown).

## Files Created
- `backend/migrations/versions/020_add_deployment_failure_columns.py` — Alembic migration adding 5 columns to `deployments`
- `frontend/src/components/charts/DeploymentTimeline.tsx` — Recharts scatter chart for deployment timeline

## Files Modified
- `backend/app/config.py` — Added `hotfix_labels`, `hotfix_branch_prefixes` settings
- `backend/app/models/models.py` — Added `is_failure`, `failure_detected_via`, `recovered_at`, `recovery_deployment_id`, `recovery_time_s` to `Deployment`
- `backend/app/schemas/schemas.py` — Extended `DeploymentDetail` and `DORAMetricsResponse`
- `backend/app/services/github_sync.py` — Changed sync to fetch all completed runs; added `detect_deployment_failures()`
- `backend/app/services/stats.py` — Added `_cfr_band()`, `_mttr_band()`, `_overall_dora_band()`; extended `get_dora_metrics()`
- `backend/tests/unit/test_dora_metrics.py` — Added 23 new tests (47 total)
- `backend/tests/integration/test_dora_api.py` — Added 2 new tests (5 total)
- `frontend/src/utils/types.ts` — Extended TS interfaces
- `frontend/src/pages/insights/DoraMetrics.tsx` — Full rewrite with 6 metric cards, 5 band indicators, timeline, enhanced table
