# Task P2-04: Issue-to-PR Linkage via Closing Keywords

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 04-github-sync-service

## Blocks
- P3-03-issue-quality-scoring
- P3-04-issue-creator-analytics

## Description
Parse closing keywords from PR bodies to link issues to the PRs that resolved them. This is the single most important gap for understanding management-created friction and the foundation for issue quality analysis. Currently, issues and PRs are tracked completely independently.

## Deliverables

- [x] **Database migration** — `closes_issue_numbers` JSONB nullable column on `pull_requests`
- [x] **Sync parser** — `extract_closing_issue_numbers(body)` with regex, called in `upsert_pull_request()`
- [x] **Stats function** — `get_issue_linkage_stats(db, team, date_from, date_to)` returning 5 linkage metrics
- [x] **Schema** — `IssueLinkageStats` Pydantic model
- [x] **API endpoint** — `GET /api/stats/issue-linkage` (admin-only, date_from/date_to/team params)
- [x] **Unit tests** — 11 tests for keyword parser (all variants, case-insensitive, dedup, false positives)
- [x] **Integration tests** — 6 tests for endpoint (empty, linked, unlinked, multiple PRs, auth, team filter)

## Files Created
- `backend/migrations/versions/004_merge_003_heads.py` — merge migration for parallel 003 heads
- `backend/migrations/versions/005_add_closes_issue_numbers_to_prs.py` — adds JSONB column
- `backend/tests/unit/test_closing_keywords.py` — 11 unit tests
- `backend/tests/integration/test_issue_linkage_api.py` — 6 integration tests

## Files Modified
- `backend/app/models/models.py` — added `closes_issue_numbers` to PullRequest
- `backend/app/services/github_sync.py` — added `extract_closing_issue_numbers()` + call in upsert
- `backend/app/services/stats.py` — added `get_issue_linkage_stats()`
- `backend/app/schemas/schemas.py` — added `IssueLinkageStats`
- `backend/app/api/stats.py` — added `/stats/issue-linkage` route
- `CLAUDE.md` — updated endpoint table, JSONB columns, completed tasks
- `docs/API.md` — added endpoint contract
