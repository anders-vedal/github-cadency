# Task 04: GitHub App Auth & Sync Service

## Phase
Phase 2 — Backend APIs

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 03-pydantic-schemas

## Blocks
- 05-webhook-endpoint
- 08-sync-control-api

## Description
Implement the GitHub sync service per spec Sections 4.1–4.4.

## Deliverables

### backend/app/services/github_sync.py

**GitHub App Authentication (Section 4.1)**
- JWT generation from App ID + private key
- Installation access token request and caching (tokens expire after 1 hour)
- Token refresh before each sync run
- httpx async client with auth headers

**Full Sync (Section 4.2 — nightly)**
1. Fetch all org repos via `GET /orgs/{org}/repos` (paginated)
2. Upsert into repositories table
3. For each tracked repo:
   - Fetch all PRs via `GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc`
   - For each PR: fetch detail endpoint for additions/deletions/changed_files (Section 4.4)
   - For each PR: fetch reviews via `GET /repos/{owner}/{repo}/pulls/{number}/reviews`
   - Fetch all issues via `GET /repos/{owner}/{repo}/issues?state=all` (skip items with `pull_request` key)
   - Fetch issue comments via `GET /repos/{owner}/{repo}/issues/comments?sort=updated&direction=desc`
4. Upsert all data using unique constraints
5. Compute derived fields: first_review_at, time_to_first_review_s, time_to_merge_s, time_to_close_s
6. Update last_synced_at on each repo
7. Log sync_event

**Incremental Sync (Section 4.2 — every 15 min)**
- Same as full sync but filtered by `since`/`last_synced_at`
- Stop pagination when hitting items older than last_synced_at

**Author Resolution**
- Match github_username from PR/review/issue data to developers table
- Set author_id/reviewer_id/assignee_id as nullable FK (NULL if not in team registry)

**Rate Limit Handling (Section 4.3)**
- Check `X-RateLimit-Remaining` on every response
- Pause and wait until `X-RateLimit-Reset` if remaining < 100
- Log rate limit events

**Deduplication**
- All upserts use unique constraints (repo_id + number for PRs/issues, github_id for reviews/comments)
