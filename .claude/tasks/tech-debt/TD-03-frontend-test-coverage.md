# TD-03: Frontend Test Coverage

## Status: TODO
## Priority: MEDIUM
## Effort: High (multi-day)

## Summary

The frontend has 3 test files (`api.test.ts`, `StatCard.test.tsx`, `useDevelopers.test.tsx`) covering 50+ components, 20+ pages, 15+ hooks, and several utility modules. Vitest is configured with jsdom and `@testing-library/react` but essentially unused. This creates high regression risk in complex UI logic.

## Current State

- **Vitest config:** `frontend/vitest.config.ts` — configured with jsdom, setup file at `src/test/setup.ts`
- **Dev deps installed:** `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `vitest`
- **Existing tests:** `StatCard.test.tsx` (5 render tests), `useDevelopers.test.tsx` (5 hook tests), `api.test.ts` (api utility tests)

## Tasks (prioritized by risk)

### Phase 1: Critical hooks (highest regression risk)
These hooks contain business logic and are consumed across many pages:

- [ ] `hooks/useStats.ts` (341 lines) — all metric fetching, complex query params
- [ ] `hooks/useNotifications.ts` — notification CRUD, config, evaluation
- [ ] `hooks/useSync.ts` — sync lifecycle, polling, adaptive intervals
- [ ] `hooks/useAI.ts` — AI mutations, cost estimates, dedup handling
- [ ] `hooks/useGoals.ts` — goal CRUD, metric computation

**Pattern:** Follow `useDevelopers.test.tsx` — wrap with `QueryClientProvider`, mock `apiFetch`, assert query keys and mutation behavior.

### Phase 2: Utility modules
- [ ] `utils/format.ts` — `timeAgo`, `formatDuration`, `formatDate` (pure functions, easy to test)
- [ ] `utils/logger.ts` — structured logger, batching, backend ingestion
- [ ] `utils/categoryConfig.ts` — `CATEGORY_CONFIG`, `CATEGORY_ORDER`

### Phase 3: Complex page components (highest blast radius)
- [ ] `pages/Dashboard.tsx` — renders stat cards, alert summary bar, charts
- [ ] `pages/DeveloperDetail.tsx` (905 lines) — profile, stats, activity, relationships, works-with
- [ ] `pages/TeamRegistry.tsx` (648 lines) — active/inactive tabs, deactivation flow
- [ ] `pages/insights/Benchmarks.tsx` — group tabs, percentile tables, team comparison
- [ ] `pages/insights/CollaborationMatrix.tsx` — heatmap, pairs table, pair detail sheet

### Phase 4: Shared components
- [ ] `components/NotificationCenter/` — bell, panel, alert summary bar
- [ ] `components/PairDetailSheet.tsx` — collaboration pair slide-over
- [ ] `components/DateRangePicker.tsx` — date range selection
- [ ] `components/charts/` — TrendChart, PercentileBar, ReviewQualityDonut

## Testing Patterns

```tsx
// Hook test pattern (established in useDevelopers.test.tsx)
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const wrapper = ({ children }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

// Component test pattern
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
// Wrap with MemoryRouter + QueryClientProvider + DateRangeContext as needed
```

## Acceptance Criteria

- [ ] Phase 1 complete: all critical hooks have tests
- [ ] Phase 2 complete: utility functions tested
- [ ] `pnpm test` runs in CI (see TD-02)
- [ ] New components/hooks include tests going forward

## Notes

- Don't mock TanStack Query internals — mock `apiFetch` at the network boundary
- Use `MemoryRouter` for components that use `react-router-dom` hooks
- Pages that consume `DateRangeContext` need a test wrapper providing it
- Chart components may need snapshot tests rather than behavioral tests
