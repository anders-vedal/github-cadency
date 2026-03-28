# Task 05: Webhook Endpoint with Signature Verification

## Phase
Phase 2 — Backend APIs

## Status
completed

## Blocked By
- 04-github-sync-service

## Blocks
None

## Description
Implement the GitHub webhook receiver per spec Sections 4.2 and 5.4.

## Deliverables

### backend/app/api/webhooks.py

**POST /api/webhooks/github**
- No bearer token auth (uses its own HMAC verification)
- Verify `X-Hub-Signature-256` header using GITHUB_WEBHOOK_SECRET
- Return 401 if signature invalid

**Event handling:**
- `pull_request` — upsert PR entity, re-fetch reviews for the PR
- `pull_request_review` — upsert review entity
- `issues` — upsert issue entity
- `issue_comment` — upsert comment entity

**Implementation details:**
- Parse `X-GitHub-Event` header to determine event type
- Parse `action` field from payload (opened, closed, edited, etc.)
- Reuse upsert logic from github_sync service
- For pull_request events, also fetch PR detail (additions/deletions) and reviews
- Compute derived fields (time_to_first_review_s, etc.) on upsert
- Handle duplicate webhooks naturally via upsert on unique constraints
- Return 200 with acknowledgment body
