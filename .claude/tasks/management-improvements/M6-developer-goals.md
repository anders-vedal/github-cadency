# Task M6: Developer Goals

## Phase
Management Phase 2 — Phase 3 (new table + CRUD + frontend)

## Status
completed

## Blocked By
- 02-sqlalchemy-models
- 07-stats-service
- 10-frontend-scaffold

## Blocks
- M7-one-on-one-prep-brief

## Description
Add a developer goals system with CRUD, progress tracking against metrics, and auto-achievement detection. Corresponds to DEVPULSE_MANAGEMENT_FEATURES.md section M6.

## Deliverables

### Database migration
New table `developer_goals`:

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| developer_id | FK -> developers | NOT NULL |
| title | varchar(255) | e.g. "Reduce avg PR size" |
| description | text | Longer context |
| metric_key | varchar(100) | Which metric to track |
| target_value | float | The target number |
| target_direction | varchar(10) | "below" or "above" |
| baseline_value | float | Value when goal was set |
| status | varchar(20) | active, achieved, abandoned |
| created_at | timestamptz | |
| target_date | date | Optional deadline |
| achieved_at | timestamptz | |
| notes | text | Manager notes |

Valid metric_key values: avg_pr_additions, time_to_merge_h, reviews_given, review_quality_score, prs_merged, time_to_first_review_h, issues_closed, etc.

### backend/app/models/developer_goal.py (new)
SQLAlchemy model for developer_goals table with relationship to Developer.

### backend/app/services/goals.py (new)
- CRUD operations for goals
- Progress computation: query current metric value from stats service, build time series history
- Auto-achievement: when metric crosses target for 2 consecutive periods, mark as `achieved` (no notification — manager confirms in 1:1)
- Status transitions: active -> achieved, active -> abandoned

### backend/app/api/goals.py (new)
- `POST /api/goals` — create goal for a developer
- `GET /api/goals?developer_id=5` — list goals for a developer
- `PATCH /api/goals/{id}` — update goal (status, notes)
- `GET /api/goals/{id}/progress` — current metric value vs target over time, returns time series history

### backend/app/schemas/ (extend)
- `GoalCreate` schema: developer_id, title, description, metric_key, target_value, target_direction, target_date
- `GoalUpdate` schema: status, notes (partial update)
- `GoalResponse` schema: all fields
- `GoalProgressResponse` schema: goal_id, title, target_value, target_direction, baseline_value, current_value, status, history array

### Frontend: goal management on Developer Detail page
- Goals section showing active goals with progress bars
- "Add Goal" form with metric key selector, target value, direction
- Progress sparkline per goal
- Status toggle (active/achieved/abandoned)
