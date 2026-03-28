# Task P4-01: DORA Metrics (Deploy Frequency + Change Lead Time)

## Phase
Phase 4 — Make It Best-in-Class

## Status
completed

## Blocked By
- P3-07-ci-check-runs

## Blocks
None

## Description
Implement the two most accessible DORA metrics using GitHub Actions as the deployment signal. DORA (Deployment Frequency, Lead Time for Changes, Change Failure Rate, Mean Time to Recovery) is the industry standard framework for measuring software delivery. Without DORA metrics, DevPulse is difficult to justify to leadership who think in DORA terms.

This task focuses on the two metrics achievable with GitHub data alone: Deploy Frequency and Change Lead Time. Change Failure Rate and MTTR require incident management integration (out of scope).

## Deliverables

### Database migration
- [x] New table: `deployments` with id, repo_id (FK), environment, sha, deployed_at, workflow_name, workflow_run_id (BigInteger), status, lead_time_s
- [x] Migration `012_add_deployments.py` with indexes on repo_id and deployed_at

### backend/app/services/github_sync.py (extend)
- [x] `upsert_deployment()` — upsert from GitHub Actions workflow run data
- [x] `compute_deployment_lead_times()` — compute lead_time_s per deployment from oldest undeployed merged PR
- [x] `sync_deployments()` — fetch workflow runs from `/actions/runs` API, filtered by `DEPLOY_WORKFLOW_NAME`
- [x] Integration into `sync_repo()` after repo tree sync (skipped if `DEPLOY_WORKFLOW_NAME` empty)

### backend/app/services/stats.py (extend)
- [x] `get_dora_metrics()` — deploy frequency, lead time, DORA band classifications, recent deployments list
- [x] `_deploy_frequency_band()` — elite/high/medium/low per DORA benchmarks
- [x] `_lead_time_band()` — elite/high/medium/low per DORA benchmarks

### backend/app/schemas/schemas.py (extend)
- [x] `DORAMetricsResponse` with deploy_frequency, deploy_frequency_band, avg_lead_time_hours, lead_time_band, total_deployments, period_days, deployments list
- [x] `DeploymentDetail` with id, repo_name, environment, sha, deployed_at, workflow_name, status, lead_time_hours

### backend/app/api/stats.py (extend)
- [x] `GET /api/stats/dora` — admin only, date_from/date_to/repo_id query params

### backend/app/config.py (extend)
- [x] `DEPLOY_WORKFLOW_NAME` (String, default "") — empty disables sync
- [x] `DEPLOY_ENVIRONMENT` (String, default "production")

### Frontend
- [x] `/insights/dora` page with stat cards, band indicator cards, deployments table, "not configured" empty state
- [x] `useDoraMetrics` hook in `useStats.ts`
- [x] `DORAMetricsResponse` and `DeploymentDetail` TypeScript interfaces
- [x] Nav entry in Insights dropdown, route in App.tsx

### Tests
- [x] 22 unit tests (band classification boundaries, get_dora_metrics with various scenarios)
- [x] 4 integration tests (API endpoint, repo filter, admin auth, empty state)

## Deviations from spec
- Used workflow runs API (`/actions/runs`) instead of GitHub Deployments API — created follow-up task P4-01b for Deployments API support
- First deployment in a repo gets `lead_time_s = NULL` (no prior deployment as reference) instead of computing against all historical PRs
- Schema named `DORAMetricsResponse` (not `DORAMetrics`) to match project convention for response models

## Files Created
- `backend/migrations/versions/012_add_deployments.py`
- `backend/tests/unit/test_dora_metrics.py`
- `backend/tests/integration/test_dora_api.py`
- `frontend/src/pages/insights/DoraMetrics.tsx`
- `.claude/tasks/improvements/P4-01b-dora-deployments-api.md`

## Files Modified
- `backend/app/models/models.py` — added `Deployment` model, `BigInteger` import, relationship on `Repository`
- `backend/app/config.py` — added `deploy_workflow_name`, `deploy_environment`
- `backend/app/schemas/schemas.py` — added `DeploymentDetail`, `DORAMetricsResponse`
- `backend/app/services/github_sync.py` — added `upsert_deployment`, `compute_deployment_lead_times`, `sync_deployments`; imported `Deployment`; added sync call in `sync_repo`
- `backend/app/services/stats.py` — added `get_dora_metrics`, `_deploy_frequency_band`, `_lead_time_band`; imported `Deployment`, `DORAMetricsResponse`, `DeploymentDetail`
- `backend/app/api/stats.py` — added `/stats/dora` route; imported `DORAMetricsResponse`, `get_dora_metrics`
- `frontend/src/utils/types.ts` — added `DeploymentDetail`, `DORAMetricsResponse` interfaces
- `frontend/src/hooks/useStats.ts` — added `useDoraMetrics` hook; imported `DORAMetricsResponse`
- `frontend/src/components/Layout.tsx` — added DORA Metrics to Insights nav dropdown
- `frontend/src/App.tsx` — added import and route for DoraMetrics page
- `.env.example` — added `DEPLOY_WORKFLOW_NAME`, `DEPLOY_ENVIRONMENT`
- `CLAUDE.md` — updated schema count, sync flow, env vars, API table, completed tasks list
- `docs/API.md` — added full DORA endpoint documentation
