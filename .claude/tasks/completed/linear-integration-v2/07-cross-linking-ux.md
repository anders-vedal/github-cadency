# Phase 7: Cross-Linking UX — Sprint on DeveloperDetail, Project Health on Dashboard

> Priority: Medium | Effort: Medium | Impact: High (polish and "aha" moments)
> Prerequisite: Phases 2-5 (data wiring must be in place)
> Related: All frontend pages that display developer or team data

## Status: Completed

## Problem

Even after Phases 2-5 wire Linear data into stats, benchmarks, AI, and notifications, the integration still feels bolted on. The Linear pages (Sprints, Planning, Projects) are self-contained islands. The core pages — Dashboard, DeveloperDetail, Executive view — don't surface sprint context.

This phase makes the integration feel native by embedding sprint/planning data into existing pages where users already spend their time.

## Changes

### 7.1 DeveloperDetail: Active Sprint Card

**File:** `frontend/src/pages/DeveloperDetail.tsx`

Add an "Active Sprint" card below the stats grid (only visible when Linear is configured and the developer is identity-mapped):

```
┌─────────────────────────────────────────┐
│ Active Sprint: Sprint 24                │
│ ████████████░░░░░░ 8/12 issues (67%)    │
│ 5 days remaining · On track             │
│                                         │
│ Recent: Sprint 23 (87%) · Sprint 22 (92%)│
└─────────────────────────────────────────┘
```

**Data source:** New endpoint `GET /developers/{id}/sprint-summary` that returns:
- Active sprint name, dates, issue completion (personal)
- Last 3 sprints personal completion rates
- Whether they're on track (completion % >= elapsed % of sprint)

**Backend:** Add to `sprint_stats.py`:
```python
async def get_developer_sprint_summary(
    db: AsyncSession, developer_id: int
) -> DeveloperSprintSummary | None:
    """Sprint summary for a specific developer. Returns None if not mapped."""
```

Query `ExternalIssue` joined to `ExternalSprint` filtered by `assignee_developer_id`.

**Visibility:** Only show when:
1. Active Linear integration exists
2. Developer has a `developer_identity_map` row
3. At least one sprint has data for this developer

### 7.2 DeveloperDetail: Linear Issues Tab

Add an "Issues" tab or section on DeveloperDetail (alongside existing PR list, reviews, goals) showing the developer's Linear issues:

```
┌──────────────────────────────────────────────────┐
│ Linear Issues (12 active)                        │
│                                                  │
│ In Progress (3)                                  │
│  ENG-456  Fix auth timeout          P1  3pts     │
│  ENG-489  Add retry logic           P2  2pts     │
│  ENG-501  Update API docs           P3  1pt      │
│                                                  │
│ Todo (4)                                         │
│  ENG-512  Migrate user settings     P2  5pts     │
│  ...                                             │
└──────────────────────────────────────────────────┘
```

**Data source:** `GET /developers/{id}/linear-issues?status_category=in_progress,todo&limit=20`

**Backend:** Add to `sprints.py` or a new developer-scoped endpoint:
```python
@router.get("/developers/{developer_id}/linear-issues")
async def get_developer_linear_issues(developer_id: int, ...):
    """List Linear issues assigned to a developer."""
```

Each issue links to Linear (via `ExternalIssue.url`). Show linked PR if `pr_external_issue_links` has a match.

### 7.3 Dashboard: Sprint Velocity Sparkline

**File:** `frontend/src/pages/Dashboard.tsx`

Add a small sprint velocity sparkline card to the dashboard stat cards row (only when Linear is active):

```
┌────────────────────┐
│ Sprint Velocity    │
│ ▃▅▆▄▇ 42 pts/sprint│
│ ↑ 12% vs avg      │
└────────────────────┘
```

**Data source:** Reuse `useSprintVelocity()` hook. The data is already cached by TanStack Query if the user visited the Sprint Dashboard.

**Conditional rendering:** Only render when `useIntegrations()` returns an active Linear integration.

### 7.4 Dashboard: Work Alignment Stat Card

Add a work alignment card alongside the velocity sparkline:

```
┌────────────────────┐
│ Work Alignment     │
│ ████████░░ 78%     │
│ PRs linked to plan │
└────────────────────┘
```

**Data source:** Reuse `useWorkAlignment()` hook.

### 7.5 Executive View: Planning Health Section

If an executive/summary view exists, add a "Planning Health" section with:
- Sprint completion rate trend (mini chart)
- Scope creep indicator
- At-risk projects count
- Triage queue depth

This gives executives a quick read on planning discipline alongside delivery metrics.

### 7.6 At-Risk Projects in Notification Center

**File:** `frontend/src/components/NotificationCenter/`

When Linear projects have `health = 'at_risk'` or `health = 'off_track'`, surface them as notifications. This requires a new alert type in Phase 4 (`project_at_risk`) or can be a simple frontend enhancement that queries projects and renders inline.

**Recommended:** Add as a notification alert type (Phase 4 addition):
```python
"project_at_risk": {
    "label": "Project At Risk",
    "description": "A Linear project's health status is at-risk or off-track",
    "category": "Planning",
    "default_enabled": True,
    "thresholds": {},
}
```

### 7.7 Conditional Sidebar Links

**File:** `frontend/src/components/Layout.tsx`, `frontend/src/App.tsx`

Currently, Sprint/Planning/Project sidebar links are always visible even when no Linear integration exists. Users clicking them see an empty state.

**Fix:** Conditionally render these sidebar links based on `useIntegrations()` returning an active integration. Show a subtle "Connect Linear" prompt instead when not configured. This avoids confusion and encourages setup.

**Implementation:** `useIntegrations()` is already available in the Layout. Add a simple check:

```tsx
const { data: integrations } = useIntegrations();
const hasLinear = integrations?.some(i => i.type === 'linear' && i.status === 'active');

// In sidebar items:
...(hasLinear ? [
    { label: 'Sprints', path: '/insights/sprints' },
    { label: 'Planning', path: '/insights/planning' },
    { label: 'Projects', path: '/insights/projects' },
] : [
    { label: 'Sprint Planning', path: '/admin/integrations', badge: 'Setup' },
])
```

### 7.8 PR Detail: Linked Linear Issue

When viewing PR details (if such a view exists), show the linked Linear issue from `pr_external_issue_links`:

```
Linked Issue: ENG-456 Fix auth timeout (In Progress, P1, Sprint 24)
```

This closes the loop: developer sees their PR and immediately knows which planned work item it addresses.

## New API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /developers/{id}/sprint-summary` | Active sprint + recent completion for a developer |
| `GET /developers/{id}/linear-issues` | Linear issues assigned to developer (paginated) |

## Schema Additions

```python
class DeveloperSprintSummary(BaseModel):
    active_sprint: SprintSummary | None
    recent_sprints: list[SprintSummary]  # last 3

class SprintSummary(BaseModel):
    sprint_id: int
    name: str
    start_date: date
    end_date: date
    total_issues: int
    completed_issues: int
    completion_pct: float
    on_track: bool
    days_remaining: int | None  # None for closed sprints
```

## Acceptance Criteria

- [ ] DeveloperDetail shows active sprint card when developer is mapped to Linear
- [ ] DeveloperDetail shows Linear issues tab/section
- [ ] Dashboard shows velocity sparkline when Linear is active
- [ ] Dashboard shows work alignment stat when Linear is active
- [ ] Sidebar links for Sprint/Planning/Projects are conditional on Linear being configured
- [ ] Non-configured state shows "Connect Linear" prompt instead of empty pages
- [ ] Sprint summary API returns correct personal completion data
- [ ] All new components handle "no Linear" state gracefully (no errors, no empty shells)

## Test Plan

- Unit test: `get_developer_sprint_summary()` returns correct data for mapped developer
- Unit test: `get_developer_sprint_summary()` returns None for unmapped developer
- Unit test: sprint summary `on_track` calculation is correct
- Integration test: `GET /developers/{id}/sprint-summary` returns 200 with data
- Integration test: `GET /developers/{id}/linear-issues` returns paginated list
- Frontend: verify sprint card doesn't render when Linear not configured
- Frontend: verify sidebar links change based on integration state
- Frontend: verify dashboard cards appear/disappear based on integration state
