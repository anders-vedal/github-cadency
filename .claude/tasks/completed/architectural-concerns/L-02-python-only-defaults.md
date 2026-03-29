# Task L-02: Add `server_default` to Non-Nullable Columns

## Severity
Low

## Status
done

## Blocked By
None

## Blocks
None

## Description
Several non-nullable columns rely solely on Python-side defaults without `server_default`. Rows inserted outside SQLAlchemy (direct SQL, migrations, test fixtures) would get NULL, violating the NOT NULL constraint.

### Affected Columns
- `developers.is_active` — Python default `True`, no server_default
- `developers.created_at`, `developers.updated_at` — Python `datetime.utcnow`
- `repositories.is_tracked`, `repositories.created_at`
- `developer_goals.target_direction`, `developer_goals.created_at`
- `developer_relationships.created_at`, `developer_relationships.updated_at`
- All float columns on `developer_collaboration_scores`

### Fix
Add `server_default=` to match the Python defaults. Use `server_default=sa.text("true")` for booleans, `server_default=func.now()` for timestamps. Create migration to add the defaults.

### Files
- `backend/app/models/models.py` — add server_default declarations
- `backend/migrations/versions/` — new migration
