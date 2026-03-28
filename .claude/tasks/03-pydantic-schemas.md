# Task 03: Pydantic Schemas for All API Models

## Phase
Phase 1 — Data Foundation

## Status
completed

## Blocked By
- 02-sqlalchemy-models

## Blocks
- 04-github-sync-service
- 06-team-registry-crud
- 07-stats-service
- 09-ai-analysis-service

## Description
Create all Pydantic request/response models in backend/app/schemas/schemas.py.

## Deliverables

### Developer schemas
- `DeveloperCreate` — github_username (required), display_name (required), email, role, skills, specialty, location, timezone, team, notes
- `DeveloperUpdate` — all fields optional (partial update for PATCH)
- `DeveloperResponse` — all fields including id, is_active, avatar_url, created_at, updated_at
- `DeveloperListResponse` — list of DeveloperResponse

### Stats schemas
- `DateRangeParams` — date_from, date_to (optional, default last 30 days)
- `DeveloperStatsResponse` — prs_opened, prs_merged, prs_closed_without_merge, prs_open, total_additions, total_deletions, total_changed_files, reviews_given (approved/changes_requested/commented), reviews_received, avg_time_to_first_review_hours, avg_time_to_merge_hours, issues_assigned, issues_closed, avg_time_to_close_issue_hours
- `TeamStatsResponse` — aggregated version of developer stats
- `RepoStatsResponse` — repo-level stats with top_contributors list

### Sync schemas
- `RepoResponse` — id, github_id, name, full_name, is_tracked, last_synced_at
- `RepoTrackUpdate` — is_tracked (bool)
- `SyncEventResponse` — all sync_events fields

### AI Analysis schemas
- `AIAnalyzeRequest` — analysis_type (enum: communication/conflict/sentiment), scope_type (enum: developer/team/repo), scope_id, date_from, date_to
- `AIAnalysisResponse` — all ai_analyses fields
- `AIAnalysisListResponse` — list of AIAnalysisResponse

### Webhook schemas
- Internal models for parsing GitHub webhook payloads (pull_request, pull_request_review, issues, issue_comment events)
