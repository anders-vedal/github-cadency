# Task P1-02: Actionable Dashboard with Alerts, Team Grid, and Trend Deltas

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- 11-frontend-dashboard-team
- P1-05-recharts-trend-viz

## Blocks
None

## Description
Rebuild the Dashboard from a wall of 7 static numbers into a three-zone actionable view. The backend already computes workload alerts, per-developer workload scores, and team stats — this task surfaces them in the UI.

Currently: 7 `StatCard` components with aggregate numbers, no links, no alerts, no drill-down.

## Deliverables

### Zone 1: "Needs Attention" alert strip
- Fetch `GET /api/stats/workload` on Dashboard mount
- Render `WorkloadAlert[]` as a colored alert list at the top of the page:
  - `critical` severity → red background
  - `warning` → amber
  - `info` → blue
- Alert types to render: `review_bottleneck`, `stale_prs`, `uneven_assignment`, `underutilized`
- Each alert links to the relevant developer's detail page
- If no alerts, show a green "All clear" banner

### Zone 2: Team Status Grid
- Fetch `GET /api/stats/workload` (already fetched for Zone 1)
- Render a table with one row per developer:
  - Display name (linked to `/team/{id}`)
  - Workload score badge (color-coded: green=low/balanced, amber=high, red=overloaded)
  - Open PRs authored
  - PRs waiting for review
  - Reviews given this period
- Sortable by any column
- Filterable by team dropdown

### Zone 3: Period Velocity with Trend Deltas
- Keep the existing 7 stat cards but add trend indicators
- Backend approach: make two `GET /api/stats/team` calls — one for current period, one for the previous equivalent period (same duration, shifted back)
- Display delta as "+15%" / "-8%" with up/down arrow and green (improving) / red (worsening) color
- For metrics where lower is better (time_to_merge, time_to_first_review), invert the color logic

### frontend/src/hooks/useStats.ts (extend)
- Add `useWorkload()` hook calling `GET /api/stats/workload`
- Add `useTeamStatsPrevious()` hook for the comparison period

### frontend/src/utils/types.ts (extend)
- Add TypeScript interfaces: `WorkloadResponse`, `DeveloperWorkload`, `WorkloadAlert`

### frontend/src/components/StatCard.tsx (extend)
- Add optional `trend` prop: `{ direction: 'up' | 'down' | 'stable', delta: string, positive: boolean }`
- Render delta badge with appropriate color when `trend` is provided

## Design Notes
- The dashboard should load in under 2 seconds — both API calls can be parallelized
- Use TanStack Query's `useQueries` for parallel fetches
- Quick-select date presets (Last 7d, 14d, 30d, 90d) should be added to the Layout date picker as part of this task
