# Task M-11: Add React.lazy Route-Level Code Splitting

## Severity
Medium

## Status
done

## Blocked By
None

## Blocks
None

## Description
All 30+ page components are statically imported at the top of `App.tsx`. The entire page bundle is downloaded on first load regardless of which page the user navigates to. This increases initial bundle size and time-to-interactive.

### Fix
Replace static imports with `React.lazy()` + `Suspense` for route-level components:
```tsx
const Dashboard = React.lazy(() => import('./pages/Dashboard'));
const DeveloperDetail = React.lazy(() => import('./pages/DeveloperDetail'));
// etc.
```

Wrap routes in `<Suspense fallback={<PageSkeleton />}>`. The `Layout` component and shared hooks should remain eagerly loaded.

### Files
- `frontend/src/App.tsx` — convert page imports to `React.lazy`, add `Suspense`
- May need to add default exports to page components that only have named exports

### Architecture Docs
- `docs/architecture/FRONTEND.md` — Route Map section
