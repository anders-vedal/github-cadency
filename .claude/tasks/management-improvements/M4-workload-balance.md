# Task M4: Workload Balance

## Phase
Management Phase 1 — Extends Phase 2-3 (stats + frontend)

## Status
completed

## Blocked By
- 07-stats-service
- 02-sqlalchemy-models

## Blocks
- M8-team-health-check

## Description
Add a workload balance endpoint showing per-developer load indicators and automated alerts for review bottlenecks, stale PRs, and uneven assignments. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M3.

## Deliverables

### backend/app/services/workload.py (new)
**Per-developer workload computation:**
- open_prs_authored, open_prs_reviewing, open_issues_assigned
- reviews_given_this_period, reviews_received_this_period
- prs_waiting_for_review, avg_review_wait_h

**Workload score heuristic:**
- Combine open PRs authored + reviewing + open issues, weighted by team median
- Score as: `low`, `balanced`, `high`, `overloaded`

**Alert generation (threshold rules):**
- `review_bottleneck`: reviews_given > 2x team median
- `stale_prs`: any PR waiting for first review > 48h
- `uneven_assignment`: top 20% of devs hold > 50% of open issues
- `underutilized`: developer has 0 PRs and 0 reviews in the period

Each alert includes: type, developer_id (if applicable), human-readable message.

### backend/app/api/stats.py (extend)
**GET /api/stats/workload**
- Query params: date_from, date_to, team (optional)
- Returns: developers array (with workload data per dev), alerts array

### backend/app/schemas/ (extend)
- `DeveloperWorkload` schema: all workload fields + workload_score
- `WorkloadAlert` schema: type, developer_id (optional), message
- `WorkloadResponse` schema: developers list, alerts list

### Frontend considerations (later)
Display workload as a team overview panel. Label workload score as "rough heuristic" in UI — this is directional, not precise.
