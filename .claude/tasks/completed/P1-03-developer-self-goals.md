# Task P1-03: Developer Self-Goal Creation

## Phase
Phase 1 — Make It Usable

## Status
done

## Blocked By
- P1-01-developer-self-access
- M6-developer-goals

## Blocks
None

## Description
Allow developers to create and manage their own goals using their personal token. Currently, goal creation requires the admin token, making goals a manager-imposed system rather than a developer-driven growth tool.

## Deliverables

### backend/app/api/goals.py (extend)
New endpoint: `POST /api/goals/self`
- Accepts developer personal token auth
- Uses the authenticated developer's ID (from `get_current_developer()`)
- Same `GoalCreate` schema but `developer_id` is ignored/overridden with the authenticated developer's ID
- Reuses existing `create_goal()` service function

New endpoint: `PATCH /api/goals/self/{goal_id}`
- Developer can update their own goals (target_value, target_date, status)
- Verify goal's `developer_id` matches authenticated developer
- Cannot modify goals created by admin (add `created_by` field — see below)

### Database migration
Add column to `developer_goals`:
- `created_by` (String, nullable) — `"self"` or `"admin"`, default `"admin"` for existing rows

### Frontend: Goals section on Developer Detail page
- When authenticated as developer: show "My Goals" section with:
  - List of active goals with progress bars (baseline -> current -> target)
  - "Add Goal" button opening a creation form
  - Goal creation form: metric selector (dropdown of MetricKey enum), target value, target date
  - Display 8-week sparkline per goal using the progress endpoint
- When authenticated as admin: show same view but for any developer, plus ability to create goals for them

### frontend/src/hooks/useGoals.ts (new)
- `useGoals(developerId)` — fetch goals for a developer
- `useGoalProgress(goalId)` — fetch 8-week progress
- `useCreateGoal()` — mutation for goal creation
- `useUpdateGoal()` — mutation for goal updates
