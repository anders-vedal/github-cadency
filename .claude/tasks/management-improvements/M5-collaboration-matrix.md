# Task M5: Collaboration Matrix

## Phase
Management Phase 2 — Phase 3 (new endpoint + frontend visualization)

## Status
completed

## Blocked By
- 07-stats-service
- 02-sqlalchemy-models
- 10-frontend-scaffold

## Blocks
- M8-team-health-check

## Description
Add a collaboration matrix endpoint showing reviewer-author pairs, and compute insights for silos, bus factors, isolated developers, and strongest pairs. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M7.

## Deliverables

### backend/app/services/collaboration.py (new)
**Matrix computation:**
- For each reviewer-author pair in the period, count: reviews_count, approvals, changes_requested
- Include developer metadata (id, name, team)

**Insights computation:**
- `silos`: identify team pairs with zero cross-team reviews
- `bus_factors`: for each repo, find reviewers with > 70% of all reviews — flag as bus factor risk
- `isolated_developers`: developers with 0 reviews given AND reviews received from <= 1 unique reviewer
- `strongest_pairs`: top mutual review pairs by combined review count

### backend/app/api/stats.py (extend)
**GET /api/stats/collaboration**
- Query params: date_from, date_to, team (optional)
- Returns: matrix array (reviewer/author pairs with counts), insights object

### backend/app/schemas/ (extend)
- `CollaborationPair` schema: reviewer, author, reviews_count, approvals, changes_requested
- `BusFactorEntry` schema: repo, sole_reviewer, review_share_pct
- `CollaborationInsights` schema: silos, bus_factors, isolated_developers, strongest_pairs
- `CollaborationResponse` schema: matrix list, insights

### Frontend: src/pages/Collaboration.tsx (new) or section in Team Dashboard
- Heatmap grid: reviewers on Y axis, authors on X axis, color intensity = review count
- Highlight silos and bus factors visually
- Use a simple table fallback if heatmap is complex to implement initially
