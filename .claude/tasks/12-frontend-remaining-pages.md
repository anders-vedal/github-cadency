# Task 12: Frontend — Developer Detail, Repos, Sync & AI Pages

## Phase
Phase 3 — Frontend

## Status
completed

## Blocked By
- 10-frontend-scaffold
- 07-stats-service
- 08-sync-control-api
- 09-ai-analysis-service

## Blocks
None

## Description
Build the remaining frontend pages per spec Section 7.1.

## Deliverables

### Developer Detail page (src/pages/DeveloperDetail.tsx)
- Profile card: name, role, skills, timezone, avatar
- Stats panel for selected date range (uses useDeveloperStats)
- PR list: sortable table, filterable by state (open/merged/closed)
- Review activity: reviews given + reviews received
- "Run AI Analysis" button → opens modal to configure analysis type and date range
- Past AI analysis results displayed as collapsible cards

### Repos page (src/pages/Repos.tsx)
- List of all synced repos from GET /api/sync/repos
- Columns: name, language, is_tracked (toggle switch), last_synced_at
- Toggle tracking calls PATCH /api/sync/repos/{id}/track
- Click repo → show per-repo stats (inline expand or separate view)

### Sync Status page (src/pages/SyncStatus.tsx)
- Current sync state indicator
- Sync event log: table of recent runs with status, duration, error count
- "Run Full Sync" and "Run Incremental Sync" buttons
- Auto-refresh sync events while sync is running

### AI Analysis page (src/pages/AIAnalysis.tsx)
- Analysis history table: type, scope, date range, created_at, status
- "New Analysis" form:
  - Analysis type: dropdown (communication, conflict, sentiment)
  - Scope type: dropdown (developer, team, repo)
  - Scope ID: dynamic selector based on scope type
  - Date range: uses global or custom
- Result viewer: structured display of JSON results with sections for scores, observations, recommendations
- Click history row → view full result
