# Task M1: Review Quality Signals

## Phase
Management Phase 1 — Extends Phase 2 (sync + stats)

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 04-github-sync-service
- 07-stats-service

## Blocks
- M5-one-on-one-prep-brief
- M8-team-health-check

## Description
Classify PR reviews into quality tiers at sync time and extend developer stats with review quality breakdowns. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M4.

## Deliverables

### Database migration
Add two columns to `pr_reviews`:
- `body_length` (integer, default 0)
- `quality_tier` (varchar(20), default 'minimal')

Create Alembic migration for the schema change.

### backend/app/services/github_sync.py (extend)
Compute quality tier on review upsert using these rules:
- `rubber_stamp`: state=APPROVED, body empty or < 20 chars
- `minimal`: body 20-100 chars, or state=COMMENTED with < 50 chars
- `standard`: body 100-500 chars or has inline code suggestions
- `thorough`: body > 500 chars, or review has 3+ individual review comments on the PR

Store `body_length` from the review body at sync time.

### backend/app/services/stats.py (extend)
Add to developer stats computation:
- `review_quality_breakdown`: count of reviews per tier (rubber_stamp, minimal, standard, thorough)
- `review_quality_score`: formula `(rubber_stamp * 0 + minimal * 1 + standard * 3 + thorough * 5) / total_reviews`, normalized to 0-10 scale

### backend/app/schemas/ (extend)
Add Pydantic response models for review quality breakdown and score within DeveloperStatsResponse.

### backend/app/models/pr_review.py (extend)
Add `body_length` and `quality_tier` columns to the SQLAlchemy model.
