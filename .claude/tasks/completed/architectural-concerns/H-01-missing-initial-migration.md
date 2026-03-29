# Task H-01: Add Initial Schema Migration

## Severity
High

## Status
completed

## Blocked By
None

## Blocks
None

## Description
There is no `000_initial_schema` migration that creates the base tables. Migration `001_add_app_role` has `down_revision = None` but only adds a column to an already-existing `developers` table. Running `alembic upgrade head` on a blank database fails because the tables it tries to ALTER don't exist.

### Problem
Base tables (`developers`, `repositories`, `pull_requests`, `pr_reviews`, `issues`, `issue_comments`, `sync_events`, `ai_analyses`, `developer_goals`) are expected to exist before any migration runs. Currently they must be created via `Base.metadata.create_all()` or Docker setup.

### Fix
Create a `000_initial_schema.py` migration that creates all base tables, then set `001_add_app_role.down_revision` to point to it. This makes `alembic upgrade head` self-contained on a fresh database.

### Deliverables
- [x] `backend/migrations/versions/000_initial_schema.py` — creates 10 base tables with pre-migration-001 columns
- [x] `backend/migrations/versions/001_add_app_role_to_developers.py` — `down_revision` updated to `"000_initial_schema"`
- [x] Migration chain verified (single root, all 24 revisions connected)
- [x] All 568 tests pass

## Files Created
- `backend/migrations/versions/000_initial_schema.py`

## Files Modified
- `backend/migrations/versions/001_add_app_role_to_developers.py`

### Architecture Docs
- `docs/architecture/DATA-MODEL.md` — Migration Patterns section
