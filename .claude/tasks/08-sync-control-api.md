# Task 08: Sync Control API & Scheduling

## Phase
Phase 2 — Backend APIs

## Status
completed

## Blocked By
- 04-github-sync-service

## Blocks
- 12-frontend-remaining-pages

## Description
Implement sync control endpoints per spec Section 5.3 and background scheduling.

## Deliverables

### backend/app/api/sync.py

**POST /api/sync/full**
- Trigger full org sync manually
- Run as background task (don't block response)
- Return 202 Accepted with sync event ID

**POST /api/sync/incremental**
- Trigger incremental sync manually
- Run as background task
- Return 202 Accepted with sync event ID

**GET /api/sync/repos**
- List all repos from repositories table
- Include: name, full_name, is_tracked, last_synced_at
- Ordered by full_name

**PATCH /api/sync/repos/{id}/track**
- Request body: { is_tracked: bool }
- Toggle tracking for a repo
- Return updated repo or 404

**GET /api/sync/events**
- List recent sync events (last 50)
- Ordered by started_at desc
- Returns list of SyncEventResponse

### Scheduling (APScheduler integration)
- Configure in FastAPI lifespan (startup/shutdown)
- Incremental sync: every SYNC_INTERVAL_MINUTES (default 15)
- Full sync: daily at FULL_SYNC_CRON_HOUR (default 2 AM)
- Graceful shutdown: wait for running sync to complete
