# Task 10: Frontend Scaffold & Routing

## Phase
Phase 3 — Frontend

## Status
completed

## Blocked By
- 01-project-scaffolding

## Blocks
- 11-frontend-dashboard-team
- 12-frontend-remaining-pages

## Description
Set up the React frontend application shell per spec Section 7.

## Deliverables

### Project setup
- Vite + React 18 + TypeScript
- Install dependencies: react-router-dom, @tanstack/react-query, date-fns (or similar)
- Configure vite proxy to backend API

### Routing (React Router)
- `/` — Dashboard
- `/team` — Team Registry
- `/team/:id` — Developer Detail
- `/repos` — Repos
- `/sync` — Sync Status
- `/ai` — AI Analysis

### Layout shell
- Top navigation bar with links to all pages
- Global date range picker in nav (default: last 30 days)
- Date range state shared via React context or URL params
- Responsive layout

### API client (src/utils/api.ts)
- Fetch wrapper with base URL and bearer token auth
- Error handling (401 → show auth error, 4xx/5xx → toast or error state)

### React Query setup (src/hooks/)
- QueryClient provider in App.tsx
- Stub hooks for each API domain:
  - useDevelopers, useDeveloper, useCreateDeveloper, useUpdateDeveloper
  - useDeveloperStats, useTeamStats, useRepoStats
  - useRepos, useToggleTracking
  - useSyncEvents, useTriggerSync
  - useAIAnalyze, useAIHistory

### Shared components (src/components/)
- DateRangePicker
- LoadingSpinner
- ErrorMessage
- PageHeader
