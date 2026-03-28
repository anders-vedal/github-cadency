# Task 11: Frontend — Dashboard & Team Registry Pages

## Phase
Phase 3 — Frontend

## Status
completed

## Blocked By
- 10-frontend-scaffold
- 06-team-registry-crud
- 07-stats-service

## Blocks
None

## Description
Build the Dashboard and Team Registry pages per spec Section 7.1.

## Deliverables

### Dashboard page (src/pages/Dashboard.tsx)
- Team overview cards: active developer count, total PRs this period, merge rate, avg time to review
- Sparkline trends for key metrics over last 4 weeks
- Recent activity feed: latest PRs merged, issues closed
- Uses useTeamStats hook with global date range

### Team Registry page (src/pages/TeamRegistry.tsx)
- Table of all developers showing: display_name, role, team, skills, location, timezone
- Filterable by team (dropdown) and active status (toggle)
- Sortable columns
- "Add Developer" button → opens modal
- Click row → navigates to `/team/:id` (Developer Detail)

### Add/Edit Developer modal
- Form with fields: github_username, display_name, email, role (dropdown), team, skills (tag input), specialty, location, timezone
- Create mode: POST /api/developers
- Edit mode: PATCH /api/developers/{id}
- Validation: github_username and display_name required
- Success → close modal + refetch list
