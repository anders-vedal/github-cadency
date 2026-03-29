# Task L-03: Remove Dead Code and Orphaned Files

## Severity
Low

## Status
done

## Blocked By
None

## Blocks
None

## Description
Several pieces of dead code identified during the architecture audit:

1. **`frontend/src/pages/SyncStatus.tsx`** — imports non-existent `useTriggerSync` hook. Not referenced in any route. Orphaned file from before the sync page rewrite.
2. **`useToggleTracking` invalidates `['sync-repos']`** — this cache key is never used elsewhere (the actual key is `['repos']`). The invalidation is a no-op.
3. **`ai_analyses.tokens_used`** — legacy column superseded by `input_tokens` + `output_tokens` (added in migration 013). No constraint ensures consistency. Consider deprecating.

### Fix
1. Delete `frontend/src/pages/SyncStatus.tsx`
2. Remove `['sync-repos']` invalidation from `useToggleTracking` in `frontend/src/hooks/useSync.ts`
3. (Optional) Add a note in `models.py` that `tokens_used` is legacy

### Files
- `frontend/src/pages/SyncStatus.tsx` — delete
- `frontend/src/hooks/useSync.ts` — clean up invalidation
