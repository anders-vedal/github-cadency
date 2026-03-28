# Task P2-09: Goals Management Page

## Phase
Phase 2 — Make It Smart

## Status
completed

## Blocked By
- M6-developer-goals
- P1-05-recharts-trend-viz

## Blocks
None

## Description
Build a dedicated Goals page that surfaces the fully-implemented goals API (`/api/goals`). Currently, goals have full CRUD API with 8-week progress history and auto-achievement detection, but zero frontend UI. A team lead cannot create, view, or track goals from the browser.

## Deliverables

### frontend/src/pages/Goals.tsx (new)
Route: `/goals`

**Team view (admin):**
- [x] Filter by developer (dropdown) or show all
- [x] Flat table of all goals with columns: Developer, Goal, Metric, Progress, Trend, Status, Due, Actions
  - [x] Progress bar (baseline -> current -> target)
  - [x] Status badge: active (secondary), achieved (default/green), abandoned (destructive)
  - [x] Target date with "N days remaining", "today", or "overdue" indicator
  - [x] 8-week sparkline showing progress history (GoalSparkline)
- [x] "Add Goal" button → GoalCreateDialog with developer selector

**Developer view (personal token):**
- [x] Shows only own goals
- [x] "Add Goal" button (calls `POST /api/goals/self`)
- [x] Same goal table with progress bars and sparklines

### frontend/src/components/GoalCreateDialog.tsx (new — shared component)
- [x] Extracted from DeveloperDetail inline dialog
- [x] Developer selector (admin creating for any developer)
- [x] Metric key selector with human-readable labels
- [x] Target value input with validation (rejects negative/zero/NaN)
- [x] Direction selector (above/below)
- [x] Target date picker (optional)
- [x] Exports `metricKeyLabels` for reuse

### frontend/src/hooks/useGoals.ts (extended)
- [x] `useUpdateAdminGoal()` — mutation for `PATCH /api/goals/{id}` (admin status/notes update)

### frontend/src/utils/types.ts (extended)
- [x] `GoalAdminUpdate` interface (`status`, `notes`)

### Navigation
- [x] Add "Goals" to admin nav in `Layout.tsx`
- [x] Add "My Goals" to developer nav in `Layout.tsx`
- [x] Add route in `App.tsx`: `/goals` -> `Goals` (accessible to both roles)

### DeveloperDetail.tsx refactored
- [x] Replaced ~100-line inline goal creation dialog with shared `GoalCreateDialog`
- [x] Removed unused imports (`Input`, `Label`, `Select*`, `createSelfGoal`, `createAdminGoal`, goal form state)

## Deviations from Original Spec

- **Flat table instead of grouped cards:** Spec said "goals grouped by developer" with goal cards. Implemented as a flat table with developer column and filter dropdown — more scannable and consistent with Dashboard patterns.
- **Shared GoalCreateDialog:** Spec didn't mention extracting a shared component. Created one to eliminate duplication between Goals page and DeveloperDetail.
- **useGoals.ts extended, not new:** The hooks file already existed with `useGoals`, `useGoalProgress`, `useCreateSelfGoal`, `useCreateAdminGoal`, `useUpdateSelfGoal`. Only `useUpdateAdminGoal` was added.
- **Types partially pre-existing:** `GoalResponse`, `GoalSelfCreate`, `GoalAdminCreate`, `GoalSelfUpdate`, `GoalProgressPoint`, `GoalProgressResponse` already existed. Only `GoalAdminUpdate` was added.
- **No `notes` form field in create dialog:** Spec mentioned optional notes. Kept parity with existing DeveloperDetail dialog which also omitted it. Notes are visible in the table when present.

## Files Created
- `frontend/src/pages/Goals.tsx`
- `frontend/src/components/GoalCreateDialog.tsx`

## Files Modified
- `frontend/src/hooks/useGoals.ts` — added `useUpdateAdminGoal()`
- `frontend/src/utils/types.ts` — added `GoalAdminUpdate` interface
- `frontend/src/components/Layout.tsx` — added Goals nav items for admin and developer
- `frontend/src/App.tsx` — added `/goals` route, imported Goals page
- `frontend/src/pages/DeveloperDetail.tsx` — replaced inline dialog with shared GoalCreateDialog, cleaned up imports
