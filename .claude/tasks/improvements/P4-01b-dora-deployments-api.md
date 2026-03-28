# Task P4-01b: DORA Metrics — GitHub Deployments API Support

## Phase
Phase 4 — Make It Best-in-Class

## Status
pending

## Blocked By
- P4-01-dora-metrics

## Blocks
None

## Description
Extend the DORA metrics deployment detection to support the GitHub Deployments API (`GET /repos/{owner}/{repo}/deployments`) as an alternative to workflow-run-based detection.

P4-01 implements deployment detection using GitHub Actions workflow runs filtered by `DEPLOY_WORKFLOW_NAME`. This works well for repos that use workflow-based deployments, but some repos use GitHub's native Deployments API (created by tools like Terraform, ArgoCD, or custom deploy scripts).

### Deliverables
- Add a config option `DEPLOY_DETECTION_MODE` with values: `"workflow"` (default, current behavior), `"deployments_api"`, `"both"`
- When mode includes `deployments_api`, fetch from `GET /repos/{owner}/{repo}/deployments` with environment filter
- Map deployment status from `GET /repos/{owner}/{repo}/deployments/{id}/statuses`
- Merge results with workflow-run-based deployments when mode is `"both"`, deduplicating by SHA
- Add tests for the new detection mode

### Why
The workflow-run approach requires users to know their deploy workflow name. The Deployments API is more structured and auto-populated by many deployment tools. Supporting both gives maximum flexibility.
