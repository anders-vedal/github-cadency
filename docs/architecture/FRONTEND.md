---
purpose: "Routing, component hierarchy, state management, hooks, design system, error/loading patterns"
last-updated: "2026-03-29"
related:
  - docs/architecture/OVERVIEW.md
  - docs/architecture/API-DESIGN.md
---

# Frontend Architecture

## Route Map

All routes defined in `frontend/src/App.tsx`.

| Path | Component | Auth | Notes |
|------|-----------|------|-------|
| `/login` | `Login` | None | |
| `/auth/callback` | `AuthCallback` | None | Captures JWT from OAuth redirect |
| `/` | `Dashboard` | Admin | Developers redirect to own `/team/:id` |
| `/executive` | `ExecutiveDashboard` | Admin | |
| `/team` | `TeamRegistry` | Admin | Active/Inactive toggle, deactivate/reactivate, DeactivateDialog, inactive-conflict reactivation on create |
| `/team/:id` | `DeveloperDetail` | Any | Shows "Inactive" badge when `is_active=false`. Includes RelationshipsCard (org hierarchy) and WorksWithSection (top collaborators) |
| `/goals` | `Goals` | Any | |
| `/insights/workload` | `WorkloadOverview` | Admin | SidebarLayout |
| `/insights/collaboration` | `CollaborationMatrix` | Admin | SidebarLayout |
| `/insights/benchmarks` | `Benchmarks` | Admin | SidebarLayout |
| `/insights/issue-quality` | `IssueQuality` | Admin | SidebarLayout |
| `/insights/code-churn` | `CodeChurn` | Admin | SidebarLayout |
| `/insights/ci-cd` | `CICDInsights` | Admin | SidebarLayout |
| `/insights/dora` | `DORAMetrics` | Admin | SidebarLayout |
| `/insights/investment` | `Investment` | Admin | SidebarLayout |
| `/insights/org-chart` | `OrgChart` | Admin | SidebarLayout |
| `/admin/repos` | `Repos` | Admin | SidebarLayout |
| `/admin/sync` | `SyncPage` | Admin | SidebarLayout |
| `/admin/sync/:id` | `SyncDetailPage` | Admin | SidebarLayout |
| `/admin/ai` | `AIAnalysis` | Admin | SidebarLayout |
| `/admin/ai/settings` | `AISettingsPage` | Admin | SidebarLayout |
| `/admin/slack` | `SlackSettingsPage` | Admin | SidebarLayout |

Bare `/insights` and `/admin` redirect to first sub-page. `ProtectedRoute` checks for `devpulse_token` in localStorage.

## Component Hierarchy

```
App
└─ QueryClientProvider (staleTime: 30s, retry: 1)
   └─ BrowserRouter
      └─ AppRoutes
         └─ AuthContext.Provider
            └─ DateRangeContext.Provider
               ├─ Login / AuthCallback (unprotected, eagerly loaded)
               └─ ProtectedRoute
                  └─ Layout (sticky header, top nav, date picker)
                     └─ Suspense (fallback: PageSkeleton)
                        └─ ErrorBoundary (global fallback)
                           ├─ ErrorBoundary → Dashboard / ExecutiveDashboard / DeveloperDetail / Goals (per-page)
                           ├─ SidebarLayout (insights) → ErrorBoundary → 9 lazy sub-pages
                           └─ SidebarLayout (admin) → ErrorBoundary → 7 lazy sub-pages
```

All page components are lazy-loaded via `React.lazy()`. Layout, SidebarLayout, and hooks are eagerly loaded.

### Layout (`components/Layout.tsx`)

Sticky header with `z-50`. Renders top nav adapted by role:
- **Admin**: Dashboard, Executive, Team, Insights, Goals, Admin dropdown
- **Developer**: My Stats (`/team/:id`), My Goals

`DateRangePicker` in the header sets the global date range. `isNavActive()` uses prefix matching for `/insights` and `/admin` sections.

### SidebarLayout (`components/SidebarLayout.tsx`)

Receives `items: SidebarItem[]` array. Renders sticky left sidebar (`w-48`) + content area. Active state: exact match or prefix + `/`.

### DeactivateDialog (`components/DeactivateDialog.tsx`)

Confirmation dialog for developer deactivation. Fetches `useDeactivationImpact()` when opened to show open PRs, issues, and active branches. Amber warning panel when open work exists. Triggers `useToggleDeveloperActive()` on confirm.

The inactive tab's reactivation button is implemented as a local `ReactivateButton` function component at the bottom of `TeamRegistry.tsx` (not a separate file). It calls `useToggleDeveloperActive(developerId)` with `true`.

### RelationshipsCard (`components/RelationshipsCard.tsx`)

Displays and manages developer hierarchical relationships on DeveloperDetail. Shows three rows: "Reports to", "Tech Lead", "Team Lead" — each with the linked developer avatar/name or (for admins) an "Add" button that opens a searchable developer dropdown dialog. Existing relationships have a hover-to-remove X button (admin only). Below the three rows, shows expandable lists of direct reports, tech-leads-for, and team-leads-for. Uses `useRelationships`, `useCreateRelationship`, `useDeleteRelationship` hooks.

### WorksWithSection (`components/WorksWithSection.tsx`)

Displays top 8 collaborators on DeveloperDetail in a 4-column card grid. Each card shows avatar, name, team badge, interaction count, total collaboration score %, and 5 signal breakdown bars (Reviews, Co-repos, Issue comments, Mentions, Co-assigned). Cards are clickable, navigating to the collaborator's detail page. Uses `useWorksWith` hook with global date range. Renders nothing when no collaboration data exists.

### OrgChart (`pages/insights/OrgChart.tsx`)

Tree visualization of the organization hierarchy from `reports_to` relationships. Expandable/collapsible nodes (auto-expanded to depth 2). Each node shows avatar, name, username, role badge, team badge, office, and direct report count. Team filter dropdown. "Not in hierarchy" section lists developers without reporting relationships. Uses `useOrgTree` hook.

## State Management

### TanStack Query

Global `QueryClient` in `App.tsx`: `staleTime: 30_000ms`, `retry: 1`.

Cache invalidation by query key prefix (e.g., `invalidateQueries({ queryKey: ['developers'] })` catches all variants).

### React Contexts

| Context | Location | Purpose |
|---------|----------|---------|
| `AuthContext` | `hooks/useAuth.ts` | `{user, isLoading, isAdmin, login, logout}` |
| `DateRangeContext` | `hooks/useDateRange.ts` | `{dateFrom, dateTo, setDateFrom, setDateTo}` |

### localStorage

Single key: `devpulse_token` (JWT). Written by `AuthCallback`, read by `apiFetch`, cleared on logout or 401.

## Hooks (`frontend/src/hooks/`)

### Auth & Date Range

| Hook | Purpose |
|------|---------|
| `useAuth()` | Consumes AuthContext |
| `useDateRange()` | Consumes DateRangeContext (default: last 30 days) |

### Data Fetching

| Hook | Endpoint | Cache key pattern |
|------|----------|-------------------|
| `useDevelopers(team, isActive)` | `GET /developers` | `['developers', team, isActive]` |
| `useDeveloper(id)` | `GET /developers/:id` | `['developer', id]` |
| `useDeactivationImpact(id, enabled)` | `GET /developers/:id/deactivation-impact` | `['developer', id, 'deactivation-impact']` |
| `useCreateDeveloper()` | `POST /developers` | Invalidates `['developers']`. `onError` in TeamRegistry catches `ApiError` with `detail.code === 'inactive_exists'` to show reactivation prompt |
| `useUpdateDeveloper(id)` | `PATCH /developers/:id` | Invalidates `['developers']`, `['developer', id]` |
| `useDeleteDeveloper()` | `DELETE /developers/:id` | Invalidates `['developers']` |
| `useToggleDeveloperActive(id)` | `PATCH /developers/:id` | Invalidates `['developers']`, `['developer', id]`. Used by DeactivateDialog and ReactivateButton |
| `useDeveloperStats(id, from, to)` | `GET /stats/developer/:id?include_percentiles=true` | `['developer-stats', id, from, to]` |
| `useTeamStats(team, from, to)` | `GET /stats/team` | `['team-stats', ...]` |
| `useRepoStats(id, from, to)` | `GET /stats/repo/:id` | `['repo-stats', ...]` |
| `useBenchmarks(team, from, to)` | `GET /stats/benchmarks` | `['benchmarks', ...]` |
| `useDeveloperTrends(id, periodType, periods)` | `GET /stats/developer/:id/trends` | `['developer-trends', ...]` |
| `useWorkload(team, from, to)` | `GET /stats/workload` | `['workload', ...]` |
| `useStalePRs(team, hours)` | `GET /stats/stale-prs` | `['stale-prs', ...]` |
| `useCollaboration(team, from, to)` | `GET /stats/collaboration` | `['collaboration', ...]` |
| `useCollaborationTrends(team, from, to)` | `GET /stats/collaboration/trends` | `['collaboration-trends', ...]` |
| `useRiskSummary(...)` | `GET /stats/risk-summary` | `['risk-summary', ...]` |
| `useCodeChurn(repoId, from, to)` | `GET /stats/repo/:id/churn` | `['code-churn', ...]` |
| `useWorkAllocation(team, from, to, useAi)` | `GET /stats/work-allocation` | `['work-allocation', ...]` |
| `useCIStats(from, to, repoId)` | `GET /stats/ci` | `['ci-stats', ...]` |
| `useDoraMetrics(from, to, repoId)` | `GET /stats/dora` | `['dora-metrics', ...]` |
| `useAllDeveloperStats(ids, from, to)` | Parallel `GET /stats/developer/:id` | Shared with `useDeveloperStats` |
| `useIssueCreatorStats(team, from, to)` | `GET /stats/issues/creators` | `['issue-creator-stats', ...]` |

### Sync

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useRepos()` | `GET /sync/repos` | |
| `useDiscoverRepos()` | `POST /sync/discover-repos` | Sets `['repos']` cache |
| `useToggleTracking()` | `PATCH /sync/repos/:id/track` | |
| `useSyncStatus()` | `GET /sync/status` | Adaptive poll: 3s active, 10s idle |
| `useSyncEvents()` | `GET /sync/events` | Fixed 10s poll |
| `useSyncEvent(id)` | `GET /sync/events/:id` | 3s when active, stops when done |
| `useStartSync()` | `POST /sync/start` | |
| `useResumeSync()` | `POST /sync/resume/:id` | |
| `useCancelSync()` | `POST /sync/cancel` | |
| `useForceStopSync()` | `POST /sync/force-stop` | |
| `useSyncContributors()` | `POST /sync/contributors` | |

### AI

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useAIHistory()` | `GET /ai/history` | |
| `useAIAnalysis(id)` | `GET /ai/history/:id` | |
| `useRunAnalysis()` | `POST /ai/analyze` | 429 special handling |
| `useRunOneOnOnePrep()` | `POST /ai/one-on-one-prep` | |
| `useRunTeamHealth()` | `POST /ai/team-health` | |
| `useAISettings()` | `GET /ai/settings` | |
| `useUpdateAISettings()` | `PATCH /ai/settings` | Optimistic cache update |
| `useAIUsage(days)` | `GET /ai/usage` | |
| `useAICostEstimate()` | `POST /ai/estimate` | On-demand mutation |

### Goals

| Hook | Endpoint |
|------|----------|
| `useGoals(devId)` | `GET /goals` |
| `useGoalProgress(goalId)` | `GET /goals/:id/progress` |
| `useCreateSelfGoal()` | `POST /goals/self` |
| `useCreateAdminGoal()` | `POST /goals` |
| `useUpdateAdminGoal()` | `PATCH /goals/:id` |
| `useUpdateSelfGoal()` | `PATCH /goals/self/:id` |

### Relationships & Collaboration (`hooks/useRelationships.ts`)

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useRelationships(devId)` | `GET /developers/:id/relationships` | All hierarchical relationships for a developer |
| `useCreateRelationship(devId)` | `POST /developers/:id/relationships` | Admin only |
| `useDeleteRelationship(devId)` | `DELETE /developers/:id/relationships` | Admin only |
| `useOrgTree(team?)` | `GET /org-tree` | Full org hierarchy tree |
| `useWorksWith(devId, dateFrom?, dateTo?)` | `GET /developers/:id/works-with` | Top collaborators with multi-signal scores |

### Slack Integration (`hooks/useSlack.ts`)

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useSlackConfig()` | `GET /slack/config` | Admin only. Global Slack settings. |
| `useUpdateSlackConfig()` | `PATCH /slack/config` | Admin only. Cache update + toast. |
| `useSlackTest()` | `POST /slack/test` | Admin only. Send test message. |
| `useNotificationHistory(limit?, offset?)` | `GET /slack/notifications` | Admin only. Notification audit log. |
| `useSlackUserSettings()` | `GET /slack/user-settings` | Current user's DM preferences. |
| `useUpdateSlackUserSettings()` | `PATCH /slack/user-settings` | Current user. Cache update + toast. |

`SlackSettingsPage` (`/admin/slack`): Admin-only page following the AISettings pattern — connection banner, master toggle, per-notification-type cards, threshold config, schedule config, notification history table. Auto-saves with debounced (500ms) and immediate (toggles) patterns.

`SlackPreferencesSection`: Renders on DeveloperDetail for the user's own profile. Shows Slack user ID input and per-notification-type toggles.

## API Integration (`utils/api.ts`)

`apiFetch(path, options?)`: wraps `fetch`, prepends `/api`, injects Bearer token. On 401: clears token, redirects to `/login`. Other errors: throws `ApiError(status, detail)` where `detail` is parsed JSON (`body.detail ?? body`) or raw text fallback.

`ApiError` class (`utils/api.ts`): extends `Error` with `status: number` and `detail: any`. Callers can pattern-match on structured error responses (e.g., `err instanceof ApiError && err.detail?.code === 'inactive_exists'` for deactivation conflict handling).

## Design System

### shadcn/ui (`components/ui/`)

19 primitives: accordion, badge, button, calendar, card, checkbox, dialog, input, label, popover, progress, select, separator, skeleton, switch, table, tabs, textarea, tooltip. Base-nova style, neutral base color, CSS variables, Lucide icons.

### Charts (`components/charts/`)

All Recharts 3 with `ResponsiveContainer`:

| Component | Type | Notes |
|-----------|------|-------|
| `TrendChart` | AreaChart | OLS regression line via ReferenceLine, `useId()` for unique gradient IDs |
| `PercentileBar` | Custom HTML | 4-band horizontal bar, inverts for lowerIsBetter |
| `ReviewQualityDonut` | PieChart (donut) | Score overlaid in center |
| `GoalSparkline` | LineChart (120x32) | Target as ReferenceLine |

### Toast Notifications

`sonner` library, bottom-right, 4s auto-dismiss. All mutations wrapped with success/error toasts.

## Error / Loading Patterns

### Loading

- `Dashboard`, `DeveloperDetail`: `StatCardSkeleton` grids + `TableSkeleton`
- `SyncPage`: Inline `animate-pulse` divs + `TableSkeleton`
- `SyncDetailPage`: `animate-pulse` divs only
- `AISettings`, `AIAnalysis`: Mix of `Skeleton` primitives and custom loading

### Error

- `ErrorCard`: Inline error with optional retry button
- `ErrorBoundary`: Per-route and per-section wrappers (Dashboard, ExecutiveDashboard, DeveloperDetail, Goals each wrapped individually; Insights and Admin sidebar content each have their own boundary). Global boundary kept as last-resort fallback. A crash in one page only affects that page — header, nav, and sidebar remain functional.

## Architectural Concerns

| Severity | Area | Description |
|----------|------|-------------|
| ~~High~~ | ~~Error isolation~~ | ~~Single global `ErrorBoundary` -- any page crash takes down entire UI~~ — **Resolved:** Per-route ErrorBoundary wrappers isolate failures by section |
| ~~Medium~~ | ~~Bug~~ | ~~`useCIStats` -- `repoId` filter never appended to query string~~ — **Resolved:** Builds `URLSearchParams` directly |
| ~~Medium~~ | ~~React rules~~ | ~~`CostEstimateLine` calls mutation inside `useState` initializer~~ — **Resolved:** Replaced with `useEffect` |
| Medium | Error handling | Some older callers still detect status codes via `error.message.includes('409')` instead of using `ApiError.status` |
| ~~Medium~~ | ~~Performance~~ | ~~No lazy loading -- all 30+ page components bundled in initial download~~ — **Resolved:** All pages use `React.lazy()` with `Suspense` fallback |
| ~~Medium~~ | ~~Duplication~~ | ~~`AlertStrip` and `SortableHead` copy-pasted between Dashboard and WorkloadOverview~~ — **Resolved:** Extracted to `components/AlertStrip.tsx` and `components/SortableHead.tsx` |
| ~~Low~~ | ~~Duplication~~ | ~~`CATEGORY_CONFIG` / `CATEGORY_ORDER` duplicated in ExecutiveDashboard and Investment~~ — **Resolved:** Extracted to `utils/categoryConfig.ts` |
| Low | Design system | Several pages use native `<select>` elements instead of shadcn/ui `Select` -- visual inconsistency |
| Low | Dead code | `SyncStatus.tsx` imports non-existent `useTriggerSync` -- orphaned file |
| Low | Cache key | `useToggleTracking` invalidates non-existent `['sync-repos']` key |
| Low | Error UX | Non-JSON error bodies (e.g., HTML 502) produce unreadable toast messages |
