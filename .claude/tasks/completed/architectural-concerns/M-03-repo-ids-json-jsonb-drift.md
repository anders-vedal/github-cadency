# Task M-03: Fix `repo_ids` JSON vs JSONB Schema Drift

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
`sync_events.repo_ids` is declared as `sa.JSON()` in migration 015 but as `JSONB` in the ORM model. On PostgreSQL, `JSON` and `JSONB` are different storage types — `JSON` stores raw text while `JSONB` stores parsed binary with indexing support. The ORM uses `JSONB` for new installs (via `create_all`), but databases upgraded via migrations have plain `JSON`.

### Fix
Create a migration that alters the column type from `JSON` to `JSONB`:
```sql
ALTER TABLE sync_events ALTER COLUMN repo_ids TYPE jsonb USING repo_ids::jsonb;
```

### Files
- `backend/migrations/versions/` — new migration

### Architecture Docs
- `docs/architecture/DATA-MODEL.md` — Architectural Concerns table
