# Task L-05: Add Missing ORM Relationships

## Severity
Low

## Status
done

## Blocked By
None

## Blocks
None

## Description
Two models have FK columns but no `relationship()` declarations:

1. **`DeveloperCollaborationScore`** — has `developer_a_id` and `developer_b_id` FK columns but no `relationship()` back to `Developer`. Service code cannot use ORM joins to this table.
2. **`SyncEvent.resumed_from_id`** — self-referential FK to `sync_events.id` but no `relationship()` to navigate from a resumed sync to its predecessor.

Additionally, `AIAnalysis.reused_from_id` has no FK constraint at all (plain Integer) — but adding one may be a separate concern (see M-02 pattern).

### Fix
Add `relationship()` declarations:
```python
# On DeveloperCollaborationScore
developer_a = relationship("Developer", foreign_keys=[developer_a_id])
developer_b = relationship("Developer", foreign_keys=[developer_b_id])

# On SyncEvent
resumed_from = relationship("SyncEvent", remote_side=[id], foreign_keys=[resumed_from_id])
```

### Files
- `backend/app/models/models.py`
