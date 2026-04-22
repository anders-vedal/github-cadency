---
purpose: "Routing, component hierarchy, state management, hooks, design system, error/loading patterns"
last-updated: "2026-04-22"
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
| `/team` | Redirect to `/admin/team` | — | |
| `/admin/team` | `TeamRegistry` | Admin | Active/Inactive toggle, deactivate/reactivate, DeactivateDialog, inactive-conflict reactivation on create |
| `/team/:id` | `DeveloperDetail` | Any | Shows "Inactive" badge when `is_active=false`. Includes RelationshipsCard (org hierarchy), WorksWithSection (top collaborators), ActivitySummaryCard (lifetime stats + work breakdown, own/admin only), EditProfileDialog (admin gear icon), DeactivateDialog (from edit dialog) |
| `/goals` | `Goals` | Any | |
| `/insights/workload` | `WorkloadOverview` | Admin | SidebarLayout |
| `/insights/collaboration` | `CollaborationMatrix` | Admin | SidebarLayout | Team-level heatmap + sortable/paginated pairs table, replaces N×N dev heatmap |
| `/insights/benchmarks` | `Benchmarks` | Admin | SidebarLayout |
| `/insights/issue-quality` | `IssueQuality` | Admin | SidebarLayout |
| `/insights/issue-linkage` | `IssueLinkage` | Admin | SidebarLayout | Per-developer PR-to-issue linkage rates, attention callout, sortable table with rate bars |
| `/insights/code-churn` | `CodeChurn` | Admin | SidebarLayout |
| `/insights/cicd` | `CIInsights` | Admin | SidebarLayout |
| `/insights/dora` | `DORAMetrics` | Admin | SidebarLayout |
| `/insights/investment` | `Investment` | Admin | SidebarLayout | Clickable donut charts, inline category preview, custom tooltips |
| `/insights/investment/:category` | `InvestmentCategory` | Admin | SidebarLayout | Paginated item table with recategorization dropdowns |
| `/insights/org-chart` | `OrgChart` | Admin | SidebarLayout |
| `/insights/conversations` | `IssueConversations` | Any | SidebarLayout | Phase 04 — chattiest issues + comment↔bounce scatter + first-response histogram. Linear-primary gate. |
| `/insights/flow` | `FlowAnalytics` | Any | SidebarLayout | Phase 06 — status-time distribution, regressions, triage bounces, churn. Readiness-gated (14d + 100 issues). |
| `/insights/bottlenecks` | `Bottlenecks` | Any | SidebarLayout | Phase 07 — CFD, WIP, review Gini, silos, blocked chains, ping-pong, bus factor, bimodal detection. |
| `/admin/linkage-quality` | `LinkageQuality` | Admin | SidebarLayout | Phase 02 — confidence donut + source breakdown + unlinked PRs + disagreement list + rerun linker button. |
| `/admin/repos` | `Repos` | Admin | SidebarLayout | Summary strip, search/filter/sort, table/card toggle, health indicators, deep links to insights |
| `/admin/sync` | `SyncPage` | Admin | SidebarLayout |
| `/admin/sync/:id` | `SyncDetailPage` | Admin | SidebarLayout |
| `/admin/ai` | `AIAnalysis` | Admin | SidebarLayout |
| `/admin/ai/settings` | `AISettingsPage` | Admin | SidebarLayout |
| `/admin/slack` | `SlackSettingsPage` | Admin | SidebarLayout |
| `/admin/work-categories` | `WorkCategoriesPage` | Admin | SidebarLayout | Categories table, classification rules table, batch reclassify |
| `/admin/notifications` | `NotificationSettings` | Admin | SidebarLayout | Per-alert-type toggle cards, threshold config, category exclusion, evaluation controls |

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
                           ├─ SidebarLayout (insights) → ErrorBoundary → 11 lazy sub-pages
                           └─ SidebarLayout (admin) → ErrorBoundary → 8 lazy sub-pages
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
| `useActivitySummary(id)` | `GET /developers/:id/activity-summary` | `['developer', id, 'activity-summary']`. 60s staleTime |
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
| `useWorkAllocationItems(cat, type, from, to, page, size)` | `GET /stats/work-allocation/items` | `['work-allocation-items', ...]` |
| `useRecategorizeItem()` | `PATCH /stats/work-allocation/items/:type/:id/category` | Mutation; invalidates `work-allocation` + `work-allocation-items` |
| `useCIStats(from, to, repoId)` | `GET /stats/ci` | `['ci-stats', ...]` |
| `useDoraMetrics(from, to, repoId)` | `GET /stats/dora` | `['dora-metrics', ...]` |
| `useAllDeveloperStats(ids, from, to)` | Parallel `GET /stats/developer/:id` | Shared with `useDeveloperStats` |
| `useReposSummary(from, to)` | `GET /stats/repos/summary` | `['repos-summary', ...]`, staleTime 60s |
| `useIssueCreatorStats(team, from, to)` | `GET /stats/issues/creators` | `['issue-creator-stats', ...]` |
| `useIssueLinkageByDeveloper(team, from, to)` | `GET /stats/issue-linkage/developers` | `['issue-linkage-developers', ...]` |

### Sync

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useRepos()` | `GET /sync/repos` | |
| `useDiscoverRepos()` | `POST /sync/discover-repos` | Sets `['repos']` cache |
| `useToggleTracking()` | `PATCH /sync/repos/:id/track` | |
| `useDeleteRepoData()` | `DELETE /sync/repos/:id/data` | Invalidates `['repos']` + `['repos-summary']`. Used by DeleteRepoDataDialog on `/repos` — typed-confirmation (user types `full_name`) before the mutation fires. |
| `useSyncStatus()` | `GET /sync/status` | Adaptive poll: 3s active, 10s idle |
| `useSyncEvents()` | `GET /sync/events` | Fixed 10s poll |
| `useSyncEvent(id)` | `GET /sync/events/:id` | 3s when active, stops when done |
| `useStartSync()` | `POST /sync/start` | |
| `useResumeSync()` | `POST /sync/resume/:id` | |
| `useCancelSync()` | `POST /sync/cancel` | |
| `useForceStopSync()` | `POST /sync/force-stop` | |
| `useSyncContributors()` | `POST /sync/contributors` | |
| `useSyncSchedule()` | `GET /sync/schedule` | staleTime 60s |
| `useUpdateSyncSchedule()` | `PATCH /sync/schedule` | Sets cache, invalidates status |

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

### Roles (`hooks/useRoles.ts`)

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useRoles()` | `GET /roles` | All role definitions. 5min staleTime. Used by TeamRegistry role picker. |
| `useCreateRole()` | `POST /roles` | Admin only. Invalidates `['roles']` cache. |
| `useUpdateRole()` | `PATCH /roles/:roleKey` | Admin only. Invalidates `['roles']` cache. |
| `useDeleteRole()` | `DELETE /roles/:roleKey` | Admin only. Invalidates `['roles']` cache. |

`TeamRegistry` role picker fetches roles from `useRoles()` and groups them by `contribution_category` using `<optgroup>` with labels: Code Contributors, Issue Contributors, Non-Contributors, System. Role display names come from the API (not hardcoded).

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

### Notifications (`hooks/useNotifications.ts`)

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useNotifications(options?)` | `GET /notifications` | Active alerts with read/dismiss state. 30s staleTime. Filters: severity, alertType, includeDismissed. |
| `useNotificationConfig()` | `GET /notifications/config` | Admin. Singleton config with alert_types metadata. 60s staleTime. |
| `useMarkRead()` | `POST /notifications/{id}/read` | Invalidates notifications cache. |
| `useMarkAllRead()` | `POST /notifications/read-all` | Bulk mark read. |
| `useDismissNotification()` | `POST /notifications/{id}/dismiss` | Body: {dismissType, durationDays?}. |
| `useDismissAlertType()` | `POST /notifications/dismiss-type` | Body: {alertType, dismissType, durationDays?}. |
| `useUpdateNotificationConfig()` | `PATCH /notifications/config` | Admin. Partial update. |
| `useEvaluateNotifications()` | `POST /notifications/evaluate` | Admin. Trigger on-demand evaluation. |

`NotificationBell` in Layout header (admin only): bell icon with red unread count badge. Click opens `NotificationPanel` dropdown. `NotificationPanel`: severity filter tabs, grouped notification list, per-item dismiss menu (permanent/7d/30d/mute type), read-on-click navigation. `AlertSummaryBar` replaces `AlertStrip` on Dashboard and Workload pages with compact severity count summary.

`NotificationSettings` (`/admin/notifications`): alert type cards grouped by category (Code Review, Workload, Risk, Collaboration, Trend, System), threshold inputs with debounced auto-save, contribution category exclusion, evaluation interval config + "Evaluate now" button.

### Teams (`hooks/useTeams.ts`)

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useTeams()` | `GET /teams` | All team definitions. 5min staleTime. |
| `useCreateTeam()` | `POST /teams` | Admin only. Invalidates `['teams']` cache. |
| `useUpdateTeam()` | `PATCH /teams/:id` | Admin only. Invalidates `['teams']` + `['developers']`. |
| `useDeleteTeam()` | `DELETE /teams/:id` | Admin only. Invalidates `['teams']` cache. |

`TeamCombobox` (`components/TeamCombobox.tsx`): Searchable combobox for team selection. Supports "create new team by typing" (shows `+Create "..."` when no match). Used by developer create/edit forms. `allowEmpty` prop for filter contexts.

### Work Categories (`hooks/useWorkCategories.ts`)

| Hook | Endpoint | Notes |
|------|----------|-------|
| `useWorkCategories()` | `GET /work-categories` | All categories. 5min staleTime. |
| `useCreateWorkCategory()` | `POST /work-categories` | Admin only. |
| `useUpdateWorkCategory()` | `PATCH /work-categories/:key` | Admin only. |
| `useDeleteWorkCategory()` | `DELETE /work-categories/:key` | Admin only. Non-default only. |
| `useWorkCategoryRules()` | `GET /work-categories/rules` | All rules. 5min staleTime. |
| `useCreateWorkCategoryRule()` | `POST /work-categories/rules` | Admin only. Validates regex. |
| `useUpdateWorkCategoryRule()` | `PATCH /work-categories/rules/:id` | Admin only. |
| `useDeleteWorkCategoryRule()` | `DELETE /work-categories/rules/:id` | Admin only. |
| `useReclassify()` | `POST /work-categories/reclassify` | Admin only. Batch reclassify. |
| `useScanSuggestions()` | `POST /work-categories/suggestions` | Admin only. Returns uncovered labels/issue types with usage counts and suggested categories. |
| `useBulkCreateRules()` | `POST /work-categories/rules/bulk` | Admin only. Creates multiple rules in one transaction. Invalidates `['work-category-rules']`. |
| `useCategoryConfig()` | Derived from `useWorkCategories()` | Replaces static `CATEGORY_CONFIG`. Returns `{ config, order }` with `FALLBACK_CATEGORY_CONFIG` while loading. |

`WorkCategoriesPage` (`/admin/work-categories`): Four-panel admin page — categories table (color swatch, CRUD, `exclude_from_stats` toggle), classification rules table (priority/match-type badge/CRUD), GitHub suggestions card (scan synced data for uncovered labels/issue types, review-and-approve flow with per-row editable category dropdown, approve/dismiss per row, bulk "Approve All"), and batch reclassify card. `SuggestionsCard` component manages local state for scanned results — dismissed items are not persisted (reappear on next scan). Approved suggestions create rules with priority 45 (labels) or 55 (issue types). Pattern matches `AISettingsPage`.

### Linear Insights v2 Hooks

Added by Phases 02-07. All respect `DateRangeContext` and include date params in query keys.

| File | Hooks | Endpoints | Notes |
|------|-------|-----------|-------|
| `useLinkageQuality.ts` | `useLinkageQuality(id)`, `useRelink()` | `GET /integrations/:id/linkage-quality`, `POST /integrations/:id/relink` | Phase 02. Admin-only. |
| `useLinearUsageHealth.ts` | `useLinearUsageHealth(from, to)` | `GET /linear/usage-health` | Phase 03. 5-min staleTime. Treats 409 as "hide card, not error" — returns null rather than throwing. |
| `useConversations.ts` | `useChattiestIssues(filters)`, `useCommentBounceScatter(from, to)`, `useFirstResponseHistogram(from, to)`, `useParticipantDistribution(from, to)` | `GET /conversations/*` | Phase 04. |
| `useDeveloperLinear.ts` | `useDeveloperLinearCreator(id, from, to)`, `useDeveloperLinearWorker(id, from, to)`, `useDeveloperLinearShepherd(id, from, to)` | `GET /developers/:id/linear-{creator,worker,shepherd}-profile` | Phase 05. `enabled: hasLinear && isPrimary`. API returns 403 for cross-user access. |
| `useFlowAnalytics.ts` | `useFlowReadiness()`, `useStatusTimeDistribution()`, `useStatusRegressions()`, `useTriageBounces()`, `useRefinementChurn()` | `GET /flow/*` | Phase 06. |
| `useBottlenecks.ts` | `useBottleneckSummary()`, `useCumulativeFlow()`, `useWip()`, `useReviewLoad()`, `useReviewNetwork()`, `useCrossTeamHandoffs()`, `useBlockedChains()`, `useReviewPingPong()`, `useBusFactorFiles()`, `useCycleHistogram()` | `GET /bottlenecks/*` | Phase 07. 10 hooks. |

Linear Insights v2 components:

- **`components/linear-health/LinearUsageHealthCard.tsx`** — Dashboard card rendering 5 signal rows with status pills (healthy green / warning amber / critical red) and click-through to drill pages. Gated on `hasLinear && issueSource?.source === 'linear'` in `Dashboard.tsx`.
- **`components/linear-health/CreatorOutcomeMiniTable.tsx`** — Top-3 creators with low-sample-size (`<5 PRs`) badges.
- **`components/developer/Linear{Creator,Worker,Shepherd}Section.tsx`** — Stacked `<h2>` sections on `DeveloperDetail.tsx`. Creator + Shepherd gated on `isAdmin || isOwnPage`; Worker visible to anyone when Linear primary.
- **`components/charts/CommentBounceScatter.tsx`** — Recharts ComposedChart with hand-rolled OLS regression line + R² overlay.
- **`components/charts/LorenzCurve.tsx`** — Gini visualization: cumulative-share AreaChart vs perfect-equality reference line.
- **`components/charts/CumulativeFlowDiagram.tsx`** — Stacked AreaChart across 7 status bands for CFD.

## API Integration (`utils/api.ts`)

`apiFetch(path, options?)`: wraps `fetch`, prepends `/api`, injects Bearer token. On 401: clears token, redirects to `/login`. Other errors: throws `ApiError(status, detail)` where `detail` is parsed JSON (`body.detail ?? body`) or raw text fallback.

`ApiError` class (`utils/api.ts`): extends `Error` with `status: number` and `detail: any`. Callers can pattern-match on structured error responses (e.g., `err instanceof ApiError && err.detail?.code === 'inactive_exists'` for deactivation conflict handling).

## Error Logging (`utils/logger.ts`)

Structured frontend logger that batches errors and ships them to the backend via `POST /api/logs/ingest` (no auth).

**Levels:**
- `logger.error(message, context?)` / `logger.warn(message, context?)` — shipped to backend, also logged to console
- `logger.info()` / `logger.debug()` — console-only, never shipped

**Batching:** Entries buffered in memory, flushed every 5s or when 10 entries accumulate. Uses `navigator.sendBeacon()` on page unload for reliability.

**Global error capture:** `initLogger()` (called in `main.tsx`) registers `window.onerror` and `window.onunhandledrejection` handlers.

**Integration points:**
- `ErrorBoundary.tsx` — calls `logger.error()` with error message, stack, and component stack
- `api.ts` — calls `logger.error()` on non-401 API failures with status, path, and detail
- Backend emits these as structlog entries with `source="frontend"` and `event_type="frontend.error"`, queryable in Loki alongside backend logs

## Design System

### shadcn/ui (`components/ui/`)

20 primitives: accordion, badge, button, calendar, card, checkbox, dialog, input, label, popover, progress, select, separator, sheet, skeleton, switch, table, tabs, textarea, tooltip. Base-nova style, neutral base color, CSS variables, Lucide icons. Note: `tooltip.tsx` uses `@base-ui/react/tooltip` (not `@radix-ui/react-tooltip`) and has a `"use client"` directive (Next.js convention, no-op in Vite).

### Charts (`components/charts/`)

All Recharts 3 with `ResponsiveContainer`:

| Component | Type | Notes |
|-----------|------|-------|
| `TrendChart` | AreaChart | OLS regression line via ReferenceLine, `useId()` for unique gradient IDs |
| `PercentileBar` | Custom HTML | 4-band horizontal bar, inverts for lowerIsBetter |
| `ReviewQualityDonut` | PieChart (donut) | Score overlaid in center |
| `GoalSparkline` | LineChart (120x32) | Target as ReferenceLine |
| `DeploymentTimeline` | Custom | Deployment history visualization |

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
| ~~Medium~~ | ~~Error handling~~ | ~~String-based status code detection (`error.message.includes('409')`)~~ — **Fixed**: All hooks now use `error instanceof ApiError && error.status === N` |
| ~~Medium~~ | ~~Duplication~~ | ~~`timeAgo`, `formatDuration` duplicated across 7+ files~~ — **Fixed**: Extracted to `utils/format.ts` |
| Medium | Unused hooks | `useCreateRole`, `useUpdateRole`, `useDeleteRole` in `useRoles.ts` are implemented but no admin UI for role CRUD exists — hooks ready, route not wired |
| ~~Medium~~ | ~~Performance~~ | ~~No lazy loading -- all 30+ page components bundled in initial download~~ — **Resolved:** All pages use `React.lazy()` with `Suspense` fallback |
| ~~Medium~~ | ~~Duplication~~ | ~~`AlertStrip` and `SortableHead` copy-pasted between Dashboard and WorkloadOverview~~ — **Resolved:** Extracted to `components/AlertStrip.tsx` and `components/SortableHead.tsx` |
| ~~Low~~ | ~~Duplication~~ | ~~`CATEGORY_CONFIG` / `CATEGORY_ORDER` duplicated in ExecutiveDashboard and Investment~~ — **Resolved:** Extracted to `utils/categoryConfig.ts` |
| Low | Design system | Several pages use native `<select>` elements instead of shadcn/ui `Select` -- visual inconsistency |
| Low | Dead code | `SyncStatus.tsx` imports non-existent `useTriggerSync` -- orphaned file |
| Low | Cache key | `useToggleTracking` invalidates non-existent `['sync-repos']` key |
| Low | Error UX | Non-JSON error bodies (e.g., HTML 502) produce unreadable toast messages |
| Medium | Notifications | No `refetchInterval` on `useNotifications` — the bell badge only updates on user interaction or mutation invalidation, not on a timer. New critical alerts won't appear until the user navigates or acts |
| Medium | Notifications | `ALERT_TYPE_LABELS` hardcoded in `NotificationPanel` duplicates backend `ALERT_TYPE_META` labels — will drift if alert types are added or renamed |
| Low | Notifications | `AlertSummaryBar` shows "View in notification center" as a `<span>`, not a `<Link>` — not clickable |
| Low | Notifications | `NotificationSettings.tsx` passes `error={error}` to `ErrorCard` but `ErrorCardProps` has no `error` prop — silently ignored, error detail never surfaced |
| Low | Design system | `tooltip.tsx` has `"use client"` directive (Next.js, meaningless in Vite) — copied from Next.js template |
