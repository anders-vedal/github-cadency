# Task 02: SQLAlchemy Models & Alembic Migration

## Phase
Phase 1 — Data Foundation

## Status
completed

## Blocked By
- 01-project-scaffolding

## Blocks
- 03-pydantic-schemas
- 04-github-sync-service
- 06-team-registry-crud
- 07-stats-service
- 09-ai-analysis-service

## Description
Implement all data models from spec Section 3 and set up the database layer.

## Deliverables

### backend/app/models/database.py
- Async engine creation using `create_async_engine` with DATABASE_URL
- `AsyncSessionLocal` session factory using `async_sessionmaker`
- `get_db` dependency for FastAPI route injection
- `Base` declarative base

### backend/app/models/models.py
All 8 tables from spec Section 3:

**developers** (Section 3.1)
- id (serial PK), github_username (unique, not null, indexed), display_name, email
- role (varchar 50), skills (jsonb), specialty, location, timezone, team
- is_active (default true), avatar_url, notes, created_at, updated_at

**repositories** (Section 3.2)
- id (serial PK), github_id (unique, not null), name, full_name (indexed)
- description, language, is_tracked (default true), last_synced_at, created_at

**pull_requests** (Section 3.3)
- id (serial PK), github_id, repo_id (FK), author_id (FK nullable), number
- title, body, state, is_merged, is_draft
- additions, deletions, changed_files, comments_count, review_comments_count
- created_at, updated_at, merged_at, closed_at
- first_review_at, time_to_first_review_s, time_to_merge_s, html_url
- UNIQUE(repo_id, number), INDEX on (author_id, created_at)

**pr_reviews** (Section 3.4)
- id (serial PK), github_id (unique, not null), pr_id (FK), reviewer_id (FK nullable)
- state, body, submitted_at

**issues** (Section 3.5)
- id (serial PK), github_id, repo_id (FK), assignee_id (FK nullable), number
- title, body, state, labels (jsonb)
- created_at, updated_at, closed_at, time_to_close_s, html_url
- UNIQUE(repo_id, number)

**issue_comments** (Section 3.6)
- id (serial PK), github_id (unique, not null), issue_id (FK)
- author_github_username, body, created_at

**sync_events** (Section 3.7)
- id (serial PK), sync_type, status, repos_synced, prs_upserted, issues_upserted
- errors (jsonb), started_at, completed_at, duration_s

**ai_analyses** (Section 3.8)
- id (serial PK), analysis_type, scope_type, scope_id
- date_from, date_to, input_summary, result (jsonb), raw_response
- model_used, tokens_used, triggered_by, created_at

### Alembic migration
- Generate initial migration with `alembic revision --autogenerate`
- Verify migration applies cleanly against fresh PostgreSQL
