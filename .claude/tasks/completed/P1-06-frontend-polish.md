# Task P1-06: Frontend Polish — Error States, Toasts, Skeletons, Date Presets

## Phase
Phase 1 — Make It Usable

## Status
completed

## Blocked By
- 10-frontend-scaffold

## Blocks
None

## Description
Address foundational UX gaps: error handling, loading states, mutation feedback, and date picker usability. Currently, failed queries show nothing (silent blank), loading shows plain text "Loading...", mutations have no success/error feedback, and the date picker requires manual typing.

## Deliverables

### Toast notifications
- [x] Installed `sonner` and added `<Toaster>` to `App.tsx` (bottom-right, 4s auto-dismiss, rich colors)
- [x] Wrapped all existing mutations with success/error toasts:
  - `useCreateDeveloper` → "Developer added" / "Failed to add developer"
  - `useUpdateDeveloper` → "Developer updated" / "Failed to update developer"
  - `useDeleteDeveloper` → "Developer removed" / "Failed to remove developer"
  - `useTriggerSync` → "Sync started" / "Failed to start sync"
  - `useToggleTracking` → "Repository tracking enabled/disabled" / "Failed to update tracking"
  - `useRunAnalysis` → "Analysis started" / "Analysis failed"
  - `useRunOneOnOnePrep` → "1:1 prep brief generated" / "Failed to generate 1:1 prep"
  - `useRunTeamHealth` → "Team health check generated" / "Failed to generate team health check"
  - `useCreateSelfGoal` / `useCreateAdminGoal` → "Goal created" / "Failed to create goal"
  - `useUpdateSelfGoal` → "Goal updated" / "Failed to update goal"

### Error states
- [x] Created reusable `ErrorCard` component: icon (AlertCircle), heading ("Something went wrong"), description (error message), "Try Again" button
- [x] Added error handling to every page that uses TanStack Query — check `isError` and render `ErrorCard`:
  - Dashboard, TeamRegistry, DeveloperDetail, Repos, SyncStatus, AIAnalysis
- [x] Added React `ErrorBoundary` class component wrapping page routes in `App.tsx` — catches render crashes with "Try Again" + "Go to Dashboard" fallback

### Skeleton loading
- [x] Created `Skeleton` UI primitive (`components/ui/skeleton.tsx`) — animated pulsing div
- [x] Created `StatCardSkeleton` — matches StatCard dimensions (title, value, subtitle placeholders)
- [x] Created `TableSkeleton` — configurable columns/rows/headers with skeleton cells
- [x] Replaced all "Loading..." text strings with appropriate skeletons across all 6 pages + Repos inline stats panel

### Date range presets
- [x] Created `DateRangePicker` component extracted from Layout.tsx
- [x] Quick-select buttons: "7d", "14d", "30d", "90d", "Quarter" (this quarter start to today)
- [x] Each preset sets both `dateFrom` and `dateTo` in `DateRangeContext`
- [x] Added Calendar popover (dual calendar for From/To) using `react-day-picker` + `date-fns` for custom range selection
- [x] Created `Calendar` (`components/ui/calendar.tsx`) and `Popover` (`components/ui/popover.tsx`) UI primitives using `@base-ui/react`

### 401 handling
- [x] Verified already implemented in `apiFetch()` (`utils/api.ts`): clears token from localStorage and redirects to `/login` on 401 responses. No additional work needed.

## Files Created
- `frontend/src/components/ui/skeleton.tsx` — Skeleton UI primitive
- `frontend/src/components/ui/calendar.tsx` — Calendar UI component (react-day-picker)
- `frontend/src/components/ui/popover.tsx` — Popover UI component (@base-ui/react)
- `frontend/src/components/ErrorCard.tsx` — Reusable error state card
- `frontend/src/components/ErrorBoundary.tsx` — React error boundary
- `frontend/src/components/StatCardSkeleton.tsx` — Skeleton variant for StatCard
- `frontend/src/components/TableSkeleton.tsx` — Skeleton variant for table rows
- `frontend/src/components/DateRangePicker.tsx` — Calendar popover + preset buttons

## Files Modified
- `frontend/src/App.tsx` — Added `<Toaster>`, wrapped routes with `<ErrorBoundary>`
- `frontend/src/components/Layout.tsx` — Replaced inline date picker with `<DateRangePicker>`
- `frontend/src/hooks/useDevelopers.ts` — Added toast notifications to 3 mutations
- `frontend/src/hooks/useSync.ts` — Added toast notifications to 2 mutations
- `frontend/src/hooks/useAI.ts` — Added toast notifications to 3 mutations
- `frontend/src/hooks/useGoals.ts` — Added toast notifications to 3 mutations
- `frontend/src/pages/Dashboard.tsx` — Error state + skeleton loading
- `frontend/src/pages/TeamRegistry.tsx` — Error state + skeleton loading
- `frontend/src/pages/DeveloperDetail.tsx` — Error state + skeleton loading
- `frontend/src/pages/Repos.tsx` — Error state + skeleton loading (page + inline panel)
- `frontend/src/pages/SyncStatus.tsx` — Error state + skeleton loading
- `frontend/src/pages/AIAnalysis.tsx` — Error state + skeleton loading
- `CLAUDE.md` — Documented new components and frontend patterns

## Packages Added
- `sonner` ^2.0.7 — Toast notification library
- `react-day-picker` ^9.14.0 — Calendar component for date picking

## Design Notes
- Toasts auto-dismiss after 4 seconds, non-blocking, positioned bottom-right, using sonner's rich colors mode
- Skeletons match the layout of the loaded state (StatCard dimensions, table column counts) to prevent layout shift
- Error boundary provides "Try Again" (resets error state) and "Go to Dashboard" fallback link
- Calendar popover shows dual side-by-side calendars (From + To) for intuitive range selection
- Date presets reuse `date-fns` for reliable date math (daysAgo, startOfQuarter)
