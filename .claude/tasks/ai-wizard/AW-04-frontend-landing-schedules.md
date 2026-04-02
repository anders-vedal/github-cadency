# Task AW-04: Frontend — AI Landing Page Refactor & Schedule Management UI

## Phase
AI Analysis Wizard

## Status
completed

## Blocked By
- AW-02-backend-schedule-system
- AW-03-frontend-wizard

## Blocks
- None

## Description
Refactor the AI Analysis landing page (`/admin/ai`) from its current 3-tab dialog-based layout into a clean landing page with unified history and a schedule management tab. Adds schedule table with enable/disable toggles, edit/delete actions, manual trigger, and last-run status display.

## Deliverables

### frontend/src/pages/AIAnalysis.tsx

**Full rewrite of the page:**

1. Page header section:
   - Title: "AI Analysis"
   - Subtitle: brief description
   - "New Analysis" primary `Button` as `Link` to `/admin/ai/new`
   - Budget warning banner (keep existing logic from current page)

2. `Tabs` component with two tabs: "History" and "Schedules"

**History tab:**

3. Unified history list (merge all analysis types into one list):
   - Filter bar at top: analysis type multi-select or dropdown (`All`, `Communication`, `Conflict`, `Sentiment`, `1:1 Prep`, `Team Health`)
   - Keep existing `HistoryList` component with its expandable cards, `ReusedBanner`, `AnalysisResultRenderer`, cost display
   - Each card shows: analysis_type badge, scope badge, date, triggered_by badge ("manual" / "scheduled" / "api"), cost
   - Regenerate buttons call the appropriate mutation based on `analysis_type`
   - Pagination or "Load more" if history grows large (currently limited to 50 in backend)

4. Empty state: illustration or icon + "No analyses yet. Run your first analysis to see results here." + "New Analysis" button

**Schedules tab:**

5. Schedule table:
   | Column | Content |
   |--------|---------|
   | Name | Schedule name, clickable to edit |
   | Type | Analysis type badge |
   | Scope | `{scope_type}: {scope_id}` |
   | Frequency | Human-readable from `next_run_description` |
   | Last Run | Relative time (`timeAgo`) + status badge (success=green, failed=red, budget_exceeded=amber, feature_disabled=gray, never=muted) |
   | Enabled | `Switch` toggle (shadcn/ui) — calls `useUpdateAISchedule({ is_enabled: !current })` on toggle |
   | Actions | Dropdown menu: "Edit" (navigate to `/admin/ai/new?schedule={id}`), "Run Now" (calls `useRunAISchedule`), "Delete" (confirmation dialog → `useDeleteAISchedule`) |

6. "Add Schedule" button above table: navigates to `/admin/ai/new` (user can save as schedule from the wizard confirm step)

7. Empty state for schedules tab: "No scheduled analyses. Create one from the New Analysis wizard." + "New Analysis" button

8. Schedule status badges:
   - `success`: green outline badge "Success"
   - `failed`: red outline badge "Failed"
   - `budget_exceeded`: amber outline badge "Budget Exceeded"
   - `feature_disabled`: gray outline badge "Feature Disabled"
   - Never run: muted text "Never run"

### frontend/src/components/Layout.tsx

**Nav structure — no changes needed:**

9. `/admin/ai` and `/admin/ai/settings` sidebar links remain the same. The wizard at `/admin/ai/new` doesn't need its own nav entry — it's accessed via the "New Analysis" button.

### frontend/src/components/ai/ (existing components — minor updates)

10. `AnalysisResultRenderer.tsx` — no changes needed (already handles all types)
11. `GenericAnalysisView.tsx` — no changes needed
12. `OneOnOnePrepView.tsx` — no changes needed
13. `TeamHealthView.tsx` — no changes needed

### Removed code cleanup

14. Remove from `AIAnalysis.tsx`:
    - `Dialog` import and the "New Analysis" dialog component (replaced by wizard)
    - `CostEstimateLine` local component (moved to wizard confirm step)
    - Inline 1:1 prep trigger card (replaced by wizard)
    - Inline team health trigger card (replaced by wizard)
    - `useState` for `open`, `form`, `prepDevId`, `healthTeam` (all replaced by wizard state)
    - Direct imports of `useRunAnalysis`, `useRunOneOnOnePrep`, `useRunTeamHealth` (history page no longer triggers — only wizard does, except for regenerate)

15. Keep in `AIAnalysis.tsx`:
    - `useAIHistory` for history display
    - `useAISettings` for budget warning
    - `HistoryList` component (reuse for unified history)
    - `ReusedBanner` component (used inside HistoryList)
    - `AnalysisResultRenderer` import
    - Regenerate functionality within history items (still needs the mutation hooks for force=true re-runs)

### Tests

16. Manual test plan:
    - Navigate to `/admin/ai` — see unified history with type filter + "New Analysis" button
    - Switch to Schedules tab — see empty state or schedule table
    - Toggle schedule enabled/disabled — verify toast + immediate toggle
    - Click "Run Now" on a schedule — verify toast + last_run updates
    - Click "Delete" on a schedule — verify confirmation dialog + removal
    - Click schedule name → navigates to wizard pre-filled in edit mode
    - Verify budget warning banner still shows when budget is high
    - Verify regenerate still works from history items
