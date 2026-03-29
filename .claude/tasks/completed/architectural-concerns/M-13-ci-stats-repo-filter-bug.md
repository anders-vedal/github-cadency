# Task M-13: Fix `useCIStats` Broken `repoId` Parameter

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
In `frontend/src/hooks/useStats.ts`, `useCIStats` calls `dateParams(dateFrom, dateTo)` which returns a string (via `params.toString()`), then attempts to call `.set('repo_id', ...)` on that string. This silently fails — `String.prototype.set` is undefined, so the `repoId` parameter is never appended to the query string.

The `CIInsights` page passes `repoId` when a user selects a repo filter, but the filter has no effect.

### Fix
Build `URLSearchParams` directly in `useCIStats` (or refactor `dateParams` to return the `URLSearchParams` object):
```typescript
const params = new URLSearchParams();
if (dateFrom) params.set('date_from', dateFrom);
if (dateTo) params.set('date_to', dateTo);
if (repoId) params.set('repo_id', String(repoId));
```

Check `useDoraMetrics` for the same pattern.

### Files
- `frontend/src/hooks/useStats.ts` — `useCIStats` (and potentially `useDoraMetrics`)

### Architecture Docs
- `docs/architecture/FRONTEND.md` — Architectural Concerns table
