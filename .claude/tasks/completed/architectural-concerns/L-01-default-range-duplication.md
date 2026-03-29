# Task L-01: Extract Shared `_default_range()` Utility

## Severity
Low

## Status
done

## Blocked By
None

## Blocks
None

## Description
`_default_range(date_from, date_to)` is defined identically in 5 service files: `stats.py`, `collaboration.py`, `risk.py`, `work_category.py`, and `enhanced_collaboration.py`. The function defaults to last 30 days if params are None.

### Fix
Extract to a shared utility (e.g., `backend/app/services/utils.py` or `backend/app/utils.py`) and import from all 5 files.

### Files
- `backend/app/services/stats.py`, `collaboration.py`, `risk.py`, `work_category.py`, `enhanced_collaboration.py` — remove local definitions
- New shared utility file — add the function
