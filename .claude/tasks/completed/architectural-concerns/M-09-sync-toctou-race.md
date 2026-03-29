# Task M-09: Add DB-Level Locking for Sync Concurrency

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
Sync start uses three optimistic reads (API route checks for active sync, then `run_sync()` checks again, then creates the SyncEvent) without any DB-level mutex. Between the check and the INSERT, another concurrent request could start a second sync.

In practice the window is very small and the impact is limited (two syncs running simultaneously would cause duplicate upserts, not data corruption). But it's a correctness issue that could cause confusing behavior.

### Options
1. **PostgreSQL advisory lock** — `SELECT pg_advisory_lock(1)` at the start of `run_sync()`, release in finally block. Zero schema change.
2. **SELECT ... FOR UPDATE SKIP LOCKED** — Lock the most recent SyncEvent row during the check.
3. **Unique partial index** — `CREATE UNIQUE INDEX ... ON sync_events (status) WHERE status = 'started'` prevents two `started` rows. Elegant but requires migration.

Option 1 is simplest and most appropriate for a single-server deployment.

### Files
- `backend/app/services/github_sync.py` — `run_sync()` concurrency guard

### Architecture Docs
- `docs/architecture/SERVICE-LAYER.md` — Sync Architecture section
