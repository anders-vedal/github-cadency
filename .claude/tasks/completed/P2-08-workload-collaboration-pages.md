# Task P2-08: Workload, Collaboration, and Benchmarks Frontend Pages

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- P1-05-recharts-trend-viz
- P2-01-stale-pr-endpoint
- M4-workload-balance
- M5-collaboration-matrix
- M2-team-benchmarks

## Blocks
None

## Description
Build three new frontend pages for fully-implemented backend features that have zero UI representation: Workload Overview, Collaboration Matrix, and Team Benchmarks. These are the most manager-actionable views in DevPulse.

## Deliverables

### Navigation restructure
- [x] Update `Layout.tsx` — added `NavGroup` type with `NavDropdown` component for "Insights" dropdown
- [x] Update `App.tsx` — registered `/insights/workload`, `/insights/collaboration`, `/insights/benchmarks` routes (admin-only)
- [x] "Insights" as a primary nav item with dropdown containing 3 sub-routes
- [ ] Move "Sync" to secondary position — kept in current position (no visual clutter with dropdown grouping)

### frontend/src/pages/insights/WorkloadOverview.tsx (new)
- [x] Alert section: renders all `WorkloadAlert` items with severity color coding (critical/warning/info)
- [x] Team workload grid with sortable columns: Developer (linked), Workload (horizontal bar + badge), Open PRs, Reviewing, Issues, Reviews Given, Awaiting Review (with avg wait time)
- [x] Stale PR list via shared `StalePRsSection` component consuming `GET /api/stats/stale-prs`
- [x] Sortable by any column, filterable by team
- [x] Summary stat cards: Overloaded count, PRs Awaiting Review, Active Alerts (with methodology tooltips)

### frontend/src/pages/insights/CollaborationMatrix.tsx (new)
- [x] Custom CSS grid heatmap: reviewer (rows) vs author (columns), color intensity = review count
- [x] Hover shows exact count, approvals, and changes_requested via title tooltip
- [x] Insights panel: Bus Factors, Team Silos, Isolated Developers, Strongest Pairs (4 cards)
- [x] Reciprocity indicator: `mutual` (green badge) vs `one-way` (amber badge) on strongest pairs
- [x] Team filter dropdown

### frontend/src/pages/insights/Benchmarks.tsx (new)
- [x] Percentile table: clickable rows showing p25, p50 (median), p75 per metric
- [x] Developer ranking: horizontal bar per developer with percentile band color coding
- [x] Polarity-aware: time metrics (lower is better) invert the color scheme
- [x] Sorted best-first per metric
- [x] Uses `useAllDeveloperStats` batch hook (avoids N+1 per-row queries)
- [ ] Box-and-whisker visualization — replaced with horizontal ranking bars using percentile band colors (simpler, equally informative)

### Hooks (added to existing useStats.ts)
- [x] `useBenchmarks()` — `GET /api/stats/benchmarks`
- [x] `useCollaboration()` — `GET /api/stats/collaboration`
- [x] `useAllDeveloperStats()` — batch `useQueries` for parallel developer stat fetches
- [x] `useWorkload()` and `useStalePRs()` — already existed, reused

### frontend/src/utils/types.ts (extended)
- [x] `BenchmarksResponse`, `CollaborationPair`, `BusFactorEntry`, `CollaborationInsights`, `CollaborationResponse`
- [x] `WorkloadResponse`, `DeveloperWorkload`, `WorkloadAlert`, `StalePRsResponse`, `StalePR` — already existed

### Shared component extraction
- [x] Extracted `StalePRsSection` from Dashboard into `components/StalePRsSection.tsx`
- [x] Dashboard imports shared component (no behavioral change)

## Deviations from Spec
- **Hooks location:** Spec called for `useInsights.ts` — hooks added to existing `useStats.ts` instead, following existing convention of one hooks file per API domain
- **Box-and-whisker chart:** Replaced with horizontal ranking bars using percentile band colors — equally informative, simpler, and consistent with `PercentileBar` component pattern
- **Sync nav position:** Spec suggested de-emphasizing Sync nav — kept in place since dropdown grouping already declutters the nav
- **Heatmap hover:** Shows count + approvals + changes_requested (via native `title` tooltip) instead of "average turnaround" (turnaround data not available in `CollaborationPair` response)
- **Metrics without individual stats:** `review_turnaround_h`, `additions_per_pr`, `review_rounds` show in the percentile table but display "—" in developer ranking when the backend doesn't expose these fields in individual developer stats

## Files Created
- `frontend/src/pages/insights/WorkloadOverview.tsx`
- `frontend/src/pages/insights/CollaborationMatrix.tsx`
- `frontend/src/pages/insights/Benchmarks.tsx`
- `frontend/src/components/StalePRsSection.tsx`

## Files Modified
- `frontend/src/components/Layout.tsx` — nav restructure with dropdown group
- `frontend/src/App.tsx` — 3 new routes
- `frontend/src/hooks/useStats.ts` — `useBenchmarks`, `useCollaboration`, `useAllDeveloperStats`
- `frontend/src/utils/types.ts` — 5 new interfaces
- `frontend/src/pages/Dashboard.tsx` — imports shared `StalePRsSection`
- `CLAUDE.md` — file tree, patterns, task completion list
