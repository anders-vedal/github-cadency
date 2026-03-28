# Task P3-03: Issue Quality Scoring

## Phase
Phase 3 — Make It Proactive

## Status
completed

## Blocked By
- P2-04-issue-pr-linkage

## Blocks
- P3-04-issue-creator-analytics

## Description
Add quality signals to issues so DevPulse can identify poorly-defined tasks that cause friction for developers. This captures data that is already available in the GitHub API response but never stored, and adds simple analysis of existing issue body content.

## Deliverables

### Database migration
- [x] Add columns to `issues`:
  - `comment_count` (Integer, default 0) — from `comments` key in GitHub API response
  - `body_length` (Integer, default 0) — character count of issue body
  - `has_checklist` (Boolean, default False) — True if body contains `- [ ]` or `- [x]`/`- [X]` patterns
  - `state_reason` (String(30), nullable) — `"completed"`, `"not_planned"`, or `"reopened"` from GitHub API
  - `creator_github_username` (String(255), nullable) — from `issue_data.get("user", {}).get("login")`
  - `milestone_title` (String(255), nullable) — from milestone data
  - `milestone_due_on` (Date, nullable) — from milestone data
  - `reopen_count` (Integer, default 0) — incremented on closed→open state transition during sync

### backend/app/services/github_sync.py (extend)
- [x] Extract all new fields from `issue_data` in `upsert_issue()`
- [x] Parse `milestone_due_on` from ISO date string → `Date`
- [x] Compute `body_length` and `has_checklist` from body
- [x] Detect reopen: if stored `state == "closed"` and incoming `state == "open"`, increment `reopen_count`
- [x] Clear `closed_at`/`time_to_close_s` when issue is re-opened (set to None if value absent)

### backend/app/services/stats.py (extend)
- [x] `get_issue_quality_stats()` — returns all quality metrics
- [x] `get_issue_label_distribution()` — standalone label distribution endpoint

### backend/app/api/stats.py (extend)
- [x] `GET /api/stats/issues/quality` — returns `IssueQualityStats` (admin only)
- [x] `GET /api/stats/issues/labels` — returns `dict[str, int]` (admin only)

### backend/app/schemas/schemas.py (extend)
- [x] `IssueQualityStats` Pydantic model

## Deviations from Original Spec
- Checklist regex also matches uppercase `- [X]` (GitHub accepts both)
- Label values validated as strings before aggregation (defensive against JSONB corruption)
- `closed_at` and `time_to_close_s` are now explicitly set to `None` when absent in API response (previously only set when present, could leave stale values on reopened issues)

## Files Created
- `backend/migrations/versions/007_merge_006_heads.py` — merge migration for diverged 006 heads
- `backend/migrations/versions/008_add_issue_quality_columns.py` — adds 8 columns to `issues`
- `backend/tests/integration/test_issue_quality_api.py` — 12 integration tests
- `backend/tests/unit/test_issue_quality.py` — 9 unit tests (checklist regex, body length)

## Files Modified
- `backend/app/models/models.py` — 8 new columns on `Issue` class
- `backend/app/services/github_sync.py` — `upsert_issue()` extended with quality fields + reopen detection
- `backend/app/services/stats.py` — `get_issue_quality_stats()` + `get_issue_label_distribution()`
- `backend/app/api/stats.py` — 2 new admin-only endpoints
- `backend/app/schemas/schemas.py` — `IssueQualityStats` model
