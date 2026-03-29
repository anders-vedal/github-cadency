# Task M-01: Add Missing Database Indexes

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
Several frequently-filtered columns lack indexes, causing full table scans in stats, workload, and sync status queries.

### Missing Indexes

| Table | Column(s) | Query pattern affected |
|-------|-----------|----------------------|
| `pull_requests` | `state` | Stats filter `state = 'open'` / `state = 'merged'` |
| `pull_requests` | `merged_at` | Date range stats, trend computation |
| `pull_requests` | `repo_id` | Joins to repositories (only covered by composite `ix_pr_author_created`) |
| `issues` | `state` | Workload queries filter open issues |
| `issues` | `assignee_id` | Per-developer workload queries |
| `pr_reviews` | `pr_id` | Every PR-to-reviews join |
| `pr_reviews` | `submitted_at` | Date range filtering on reviews |
| `sync_events` | `status` | Status queries run on every sync check and scheduler tick |

### Fix
1. Add indexes to `backend/app/models/models.py` via `__table_args__` or `index=True`
2. Create an Alembic migration for the new indexes

### Files
- `backend/app/models/models.py` — add index declarations
- `backend/migrations/versions/` — new migration

### Architecture Docs
- `docs/architecture/DATA-MODEL.md` — Architectural Concerns table
