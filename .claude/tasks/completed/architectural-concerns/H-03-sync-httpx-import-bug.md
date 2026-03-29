# Task H-03: Fix Missing `httpx` Import in sync.py

## Severity
High

## Status
completed

## Blocked By
None

## Blocks
None

## Description
`backend/app/api/sync.py` line 237 uses `httpx.HTTPStatusError` in an except clause, but `httpx` is never imported in the file. If `discover_org_repos()` propagates an httpx error, the except clause itself will raise `NameError: name 'httpx' is not defined`, producing an unhelpful 500 error instead of the intended error message.

### Fix
Add `import httpx` to the imports in `backend/app/api/sync.py`.

### Files
- `backend/app/api/sync.py` — add import

### Deliverables
- [x] `import httpx` added to `backend/app/api/sync.py`
- [x] All 621 tests pass

## Files Modified
- `backend/app/api/sync.py`

### Architecture Docs
- `docs/architecture/API-DESIGN.md` — Architectural Concerns table
