# Task M-14: Fix `CostEstimateLine` useState Side Effect

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
In `frontend/src/pages/AIAnalysis.tsx`, `CostEstimateLine` uses `useState` with a lazy initializer to trigger a mutation:
```typescript
useState(() => {
  estimate.mutate({ feature, ... })
})
```

This runs the mutation synchronously during render, which violates React rules (side effects must not occur during render). In React 18+ strict mode, this would fire twice in development. It should use `useEffect`.

### Fix
Replace the `useState` initializer with a `useEffect`:
```typescript
useEffect(() => {
  estimate.mutate({ feature, ... });
}, [feature, ...]);
```

### Files
- `frontend/src/pages/AIAnalysis.tsx` — `CostEstimateLine` component

### Architecture Docs
- `docs/architecture/FRONTEND.md` — Architectural Concerns table
