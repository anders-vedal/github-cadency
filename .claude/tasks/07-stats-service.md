# Task 07: Stats Service & API Endpoints

## Phase
Phase 2 — Backend APIs

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 03-pydantic-schemas

## Blocks
- 11-frontend-dashboard-team
- 12-frontend-remaining-pages

## Description
Implement stats computation and API endpoints per spec Sections 5.2.

## Deliverables

### backend/app/services/stats.py
Pure SQL computation using SQLAlchemy queries. All queries filter by date range.

**Developer stats computation:**
- PRs opened (authored, created_at in range)
- PRs merged (authored, is_merged=true, merged_at in range)
- PRs closed without merge (authored, state=closed, is_merged=false, closed_at in range)
- PRs currently open (authored, state=open)
- Total additions / deletions / changed files (sum from authored PRs in range)
- Reviews given: count by state (APPROVED, CHANGES_REQUESTED, COMMENTED)
- Reviews received: count of reviews on authored PRs
- Avg time to first review (hours) — mean of time_to_first_review_s for authored PRs
- Avg time to merge (hours) — mean of time_to_merge_s for merged PRs
- Issues assigned (assignee_id match, created_at in range)
- Issues closed (assignee_id match, closed_at in range)
- Avg time to close issue (hours) — mean of time_to_close_s

**Team stats computation:**
- Aggregate developer stats for all developers in a team
- Include developer count, total PRs, merge rate, avg review time

**Repo stats computation:**
- Per-repo totals for PRs, issues, reviews
- Top contributors list (by PR count)

### backend/app/api/stats.py

**GET /api/stats/developer/{id}**
- Query params: date_from, date_to (default last 30 days)
- Returns DeveloperStatsResponse
- 404 if developer not found

**GET /api/stats/team**
- Query params: team (optional filter), date_from, date_to
- Returns TeamStatsResponse

**GET /api/stats/repo/{id}**
- Query params: date_from, date_to
- Returns RepoStatsResponse with top_contributors
- 404 if repo not found
