# Task L-06: Fix ORM Type Annotation Mismatches

## Severity
Low

## Status
done

## Blocked By
None

## Blocks
None

## Description
Two ORM type annotations don't match the actual stored data:

1. **`developers.skills`** — ORM annotation says `dict | None` but actual data is `list[str]`. Pydantic schema exposes as `list[str] | None`.
2. **`issues.labels`** — ORM annotation says `dict | None` but GitHub returns labels as a list of objects, and `pull_requests.labels` is typed as `list | None`.

These mismatches don't cause runtime errors (JSONB stores whatever Python gives it) but mislead developers reading the model and could cause issues with type checkers.

### Fix
Update the `Mapped[]` annotations:
```python
# developers
skills: Mapped[list | None] = mapped_column(JSONB, nullable=True)

# issues
labels: Mapped[list | None] = mapped_column(JSONB, nullable=True)
```

### Files
- `backend/app/models/models.py` — `Developer.skills`, `Issue.labels`

### Architecture Docs
- `docs/architecture/DATA-MODEL.md` — Architectural Concerns table
