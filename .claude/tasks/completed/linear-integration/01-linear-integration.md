# Linear Integration: Engineering Intelligence from Planning Data

> Priority: High | Effort: Large | Impact: High
> Supersedes: `competitive-improvements/P1-03-project-tracker-integration.md` (Linear-first, Jira deferred)
> Related: `improvements/P3-02-sprint-model.md` (superseded by external sprint data)

## Status: Phase 1 Complete (Backend)

Phase 1 (Data Foundation) implemented 2026-04-06. Phase 2 (Frontend) and Phase 3 (Advanced) pending.

## Context

DevPulse tracks the **execution layer** (PRs, reviews, deployments) but has zero visibility into the **planning layer** (sprints, estimates, triage, project health). GitHub Issues lacks sprint/cycle, priority enums, story points, status workflows, and triage queues.

Linear provides all of these natively. Integrating Linear lets DevPulse answer: **"Are we planning well AND executing well?"** — correlating planning discipline with delivery outcomes.

**Core principles (unchanged):**
- Read-only — DevPulse never writes to Linear
- Linear is an additive data source alongside GitHub, not a replacement
- All existing GitHub-only functionality continues to work without Linear configured
- Developer identity mapping is admin-managed (Linear email ↔ GitHub username)

### Primary Issue Source

When Linear is configured, the admin chooses a **primary issue source** (`github` or `linear`). This controls where issue-level metrics are computed from:

| Setting | Default | Issue metrics from | Planning pages | GitHub Issues |
|---|---|---|---|---|
| `github` | Yes (always available) | GitHub Issues | Hidden | Full metrics |
| `linear` | Available when Linear connected | Linear issues | Visible (sprints, velocity, triage, etc.) | Still synced (free via GitHub API), but treated as supplementary signal only |

**Why not merge both sources?** Deduplication across GitHub Issues ↔ Linear issues is complex and error-prone (matching by title? cross-reference? manual linking?). A primary source toggle avoids double-counting and gives the admin a clean, intentional choice. GitHub Issues still sync regardless — they capture bot-created issues, external contributor reports, and monitoring alerts that may not exist in Linear.

**What switches when primary source changes:**
- Issue quality stats (`get_issue_quality_stats`) query the primary source table
- Issue linkage stats (`get_issue_linkage_stats`) check PR links against primary source
- Work category classification runs against primary source issues
- Issue creator analytics use primary source data
- Activity summary issue counts use primary source
- Notification evaluators (issue linkage alerts) use primary source thresholds

**What doesn't switch:**
- PR metrics (always from GitHub — Linear doesn't have PRs)
- Review metrics (always from GitHub)
- DORA metrics (always from GitHub deployments)
- Collaboration metrics (always from GitHub PR/review data)
- Sprint/velocity/triage/estimation (always from Linear — GitHub can't provide these)

## What This Unlocks

| Metric | Source | Why It Matters |
|--------|--------|----------------|
| Sprint velocity trend | Linear cycles | Are we getting faster or slower? |
| Sprint completion rate | Linear cycles | Do we deliver what we commit to? |
| Scope creep rate | Linear cycle history | How much unplanned work enters mid-sprint? |
| Triage latency | Linear issue state history | How fast do we accept work into the backlog? |
| Estimation accuracy | Linear points vs completion | Are estimates improving? |
| Project health trends | Linear projects | Are initiatives on track? |
| Planning ↔ delivery correlation | Linear + GitHub | Does better planning → faster delivery? |
| Work alignment | PR ↔ Linear issue linking | What % of code work is tied to planned work? |
| Priority distribution | Linear priority field | Are we drowning in urgent work? |

## Architecture

```
                  ┌──────────────┐
                  │ Linear API   │
                  │ (GraphQL)    │
                  └──────┬───────┘
                         │ OAuth 2.0 / API key
                         ▼
              ┌─────────────────────┐
              │ linear_sync.py      │
              │ - sync_teams()      │
              │ - sync_cycles()     │
              │ - sync_projects()   │
              │ - sync_issues()     │
              │ - link_prs()        │
              └──────────┬──────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌────────────┐ ┌───────────┐ ┌──────────────┐
   │ ext_sprints│ │ ext_issues│ │ pr_ext_links │
   └────────────┘ └───────────┘ └──────────────┘
          │              │              │
          ▼              ▼              ▼
   ┌─────────────────────────────────────────┐
   │ sprint_stats.py                         │
   │ - velocity, completion, scope creep     │
   │ - planning accuracy, triage latency     │
   │ - work alignment (linked vs unlinked)   │
   │ - correlation with GitHub delivery data │
   └─────────────────────────────────────────┘
```

## Phases

### Phase 1: Data Foundation (Backend)

#### New Models

**`integration_config` table:**
```
id, type ("linear"), display_name, config (JSONB, encrypted),
status ("active" | "disabled" | "error"), error_message,
is_primary_issue_source (bool, default false),
last_synced_at, created_at, updated_at
```
- `config` JSONB holds: `api_key` (encrypted), `workspace_id`, `webhook_secret`
- Encrypted using same Fernet pattern as Slack bot token (`services/slack.py`)
- Singleton per type for now (one Linear workspace)
- `is_primary_issue_source`: when `true`, issue metrics are computed from this integration's data instead of GitHub Issues. Only one integration can be primary at a time. When no integration has this set (or none configured), GitHub Issues is the default source. Toggled via `PATCH /api/integrations/{id}` or via the integration settings UI.

**`external_projects` table:**
```
id, integration_id (FK), external_id (unique), key, name,
status ("planned" | "started" | "paused" | "completed" | "cancelled"),
health ("on_track" | "at_risk" | "off_track"),
start_date, target_date, progress_pct,
lead_id (FK developers, nullable), url,
created_at, updated_at
```

**`external_sprints` table:**
```
id, integration_id (FK), external_id (unique), name, number,
team_key, team_name,
state ("active" | "closed" | "future"),
start_date, end_date,
planned_scope (int, issues at cycle start),
completed_scope (int, issues completed),
cancelled_scope (int, issues cancelled/moved out),
added_scope (int, issues added mid-cycle),
url, created_at, updated_at
```

**`external_issues` table:**
```
id, integration_id (FK), external_id (unique), identifier (e.g., "ENG-123"),
title, description_length,
issue_type ("issue" | "bug" | "feature" | "improvement" | "sub_issue"),
status, status_category ("triage" | "backlog" | "todo" | "in_progress" | "done" | "cancelled"),
priority (0-4, 0=none, 1=urgent, 4=low),
priority_label,
estimate (float, nullable, story points),
assignee_email, assignee_developer_id (FK developers, nullable),
project_id (FK external_projects, nullable),
sprint_id (FK external_sprints, nullable),
parent_issue_id (FK self, nullable),
labels (JSONB),
created_at, started_at, completed_at, cancelled_at, updated_at,
triage_duration_s (int, nullable, created → accepted),
cycle_time_s (int, nullable, started → completed),
url
```

**`developer_identity_map` table:**
```
id, developer_id (FK developers), integration_type ("linear"),
external_user_id, external_email, external_display_name,
mapped_by ("admin" | "auto"), created_at
```
- Admin maps Linear users to DevPulse developers
- Auto-mapping attempted by email match during sync

**`pr_external_issue_links` table:**
```
id, pull_request_id (FK), external_issue_id (FK),
link_source ("branch" | "title" | "body" | "linear_auto"),
created_at
```
- `linear_auto` = Linear's own GitHub integration created the link

#### New Service: `backend/app/services/linear_sync.py`

```python
class LinearClient:
    """GraphQL client for Linear API. Read-only."""
    
    async def query(self, query: str, variables: dict) -> dict: ...
    # Rate limit: 1500 requests/hour, track via response headers

async def sync_linear(db: AsyncSession, integration_id: int) -> SyncEvent:
    """Full Linear sync orchestration."""
    # 1. sync_teams() — fetch workspace teams
    # 2. sync_cycles() — active + last N closed cycles per team
    # 3. sync_projects() — all non-archived projects
    # 4. sync_issues() — issues updated since last sync
    # 5. link_prs_to_external_issues() — match by identifier in PR title/branch
    # 6. map_developers() — auto-match by email where possible

async def sync_linear_cycles(client, db, integration_id) -> int: ...
async def sync_linear_projects(client, db, integration_id) -> int: ...
async def sync_linear_issues(client, db, integration_id, since: datetime) -> int: ...

def extract_linear_keys(text: str) -> list[str]:
    """Extract Linear issue identifiers (e.g., ENG-123) from text."""
    # Pattern: [A-Z]{2,5}-\d+ (same pattern Linear uses)

async def auto_map_developers(db, integration_id) -> tuple[int, int]:
    """Auto-map Linear users to developers by email. Returns (mapped, unmapped)."""
```

#### New Service: `backend/app/services/sprint_stats.py`

```python
async def get_sprint_velocity(db, team_key: str | None, limit: int = 10) -> list[SprintVelocity]:
    """Velocity trend: completed scope per cycle over time."""

async def get_sprint_completion_rate(db, sprint_id: int) -> SprintCompletion:
    """Committed vs delivered for a specific cycle."""

async def get_scope_creep(db, sprint_id: int) -> ScopeCreep:
    """Issues added mid-cycle as % of original planned scope."""

async def get_triage_metrics(db, date_from, date_to) -> TriageMetrics:
    """Avg/p50/p90 triage duration, issues in triage, triage queue age."""

async def get_estimation_accuracy(db, team_key: str | None, limit: int = 10) -> list[EstimationAccuracy]:
    """Per-cycle: estimated points vs completed points."""

async def get_work_alignment(db, date_from, date_to) -> WorkAlignment:
    """% of PRs linked to external issues vs unlinked (unplanned work)."""

async def get_planning_delivery_correlation(db, team_key: str | None) -> PlanningCorrelation:
    """Correlate sprint completion rate with avg PR merge time per cycle."""
```

#### New Router: `backend/app/api/integrations.py`

```
POST   /api/integrations              — configure Linear (admin)
GET    /api/integrations              — list configured integrations (admin)
PATCH  /api/integrations/{id}         — update config (admin)
DELETE /api/integrations/{id}         — remove integration (admin)
POST   /api/integrations/{id}/test    — test connection (admin)
POST   /api/integrations/{id}/sync    — trigger manual sync (admin)
GET    /api/integrations/{id}/status  — sync status (admin)
GET    /api/integrations/{id}/users   — list Linear users for mapping (admin)
POST   /api/integrations/{id}/map-user — manually map Linear user → developer (admin)
GET    /api/integrations/issue-source — returns current primary issue source ("github" | "linear") + integration_id if linear
PATCH  /api/integrations/{id}/primary — set this integration as primary issue source (admin, clears other primaries)
```

#### Helper: `get_primary_issue_source()`

Shared helper used by stats/notification services to route issue queries:

```python
async def get_primary_issue_source(db: AsyncSession) -> str:
    """Returns 'github' or 'linear'. Checks integration_config for is_primary_issue_source=True."""
    result = await db.execute(
        select(IntegrationConfig).where(
            IntegrationConfig.is_primary_issue_source == True,
            IntegrationConfig.status == "active"
        )
    )
    config = result.scalar_one_or_none()
    return config.type if config else "github"
```

Issue-related stats functions (`get_issue_quality_stats`, `get_issue_linkage_stats`, `get_issue_creator_stats`, etc.) call this at the top and branch to query either `issues` (GitHub) or `external_issues` (Linear) table accordingly.

#### New Router: `backend/app/api/sprints.py`

```
GET /api/sprints                      — list cycles (with filters: team, state)
GET /api/sprints/{id}                 — cycle detail (issues, PRs, metrics)
GET /api/sprints/velocity             — velocity trend chart data
GET /api/sprints/completion           — completion rate trend
GET /api/sprints/scope-creep          — scope creep trend
GET /api/projects                     — list projects with health + progress
GET /api/projects/{id}                — project detail (milestones, issues)
GET /api/planning/triage              — triage queue metrics
GET /api/planning/alignment           — work alignment (linked vs unlinked PRs)
GET /api/planning/accuracy            — estimation accuracy trend
GET /api/planning/correlation         — planning ↔ delivery correlation
```

#### Sync Integration

- Linear sync runs on a separate schedule from GitHub sync (default: every 2 hours)
- Uses same `SyncEvent` model with `sync_type="linear"`
- Post-sync hook: `link_prs_to_external_issues()` matches PRs to Linear issues
- Developer identity mapping surfaced in integration settings UI
- Webhook receiver for real-time issue status changes (optional, Phase 2)

### Phase 2: Frontend — Sprint & Planning Insights

#### Integration Settings Page (`/admin/integrations`)
- Linear connection card: API key input (masked), workspace display, test button
- Sync status + last synced timestamp + manual sync trigger
- **Primary issue source toggle:** segmented control (`GitHub Issues` | `Linear`) — visible only when Linear is connected and active. Switching shows a confirmation dialog explaining what changes (issue metrics source, planning pages visibility). Current selection highlighted. When set to Linear, a green badge "Primary" appears on the Linear card.
- Developer mapping table: Linear user ↔ DevPulse developer, auto-match button, manual override dropdowns
- Unmapped users highlighted with warning

#### Sprint Dashboard (`/insights/sprints`)
- **Sprint selector:** dropdown of recent cycles (active highlighted)
- **Velocity chart:** bar chart (completed scope per sprint), trend line overlay
- **Completion card:** committed vs delivered (donut or stacked bar)
- **Scope creep card:** original vs final scope, % added mid-cycle
- **Sprint detail table:** issues in cycle with status, assignee, estimate, linked PRs
- **Carry-over indicator:** issues that rolled from previous cycle

#### Planning Insights (`/insights/planning`)
- **Work alignment card:** % of PRs linked to tracked work vs unplanned
- **Triage metrics:** avg triage time, queue depth, p90 triage latency
- **Estimation accuracy chart:** estimated vs actual points per cycle, trend
- **Planning ↔ delivery correlation:** scatter plot (completion rate vs avg merge time)

#### Project Portfolio (`/insights/projects`)
- **Project list:** name, health badge (green/yellow/red), progress bar, target date, lead
- **Project detail:** milestones, linked issues with status, associated PRs

#### Dashboard Integration
- Sprint velocity sparkline on main dashboard (if Linear configured)
- Work alignment % on executive dashboard
- Unplanned work ratio in workload analysis

### Phase 3: Advanced Correlations & Notifications

- **Notification evaluators:** sprint-at-risk (completion rate below threshold mid-cycle), triage queue growing, scope creep spike, project health degraded
- **Benchmarks integration:** planning metrics in peer group comparisons (velocity per dev, estimation accuracy)
- **AI analysis context:** include sprint data in 1:1 prep and team health contexts ("Developer X completed 85% of sprint commitments, but their PRs averaged 48h merge time")
- **Linear webhooks:** real-time sync for issue status changes instead of polling

## Config

```env
# Linear integration (optional)
LINEAR_API_KEY=lin_api_...           # or configured via UI
LINEAR_WEBHOOK_SECRET=...            # for real-time sync (Phase 3)
LINEAR_SYNC_INTERVAL_MINUTES=120     # default 2 hours
```

## Security

- API keys encrypted at rest using existing Fernet pattern
- Read-only access — DevPulse never writes to Linear
- Integration config is admin-only
- Linear API key scoped to read permissions only

## Testing

- Unit test `extract_linear_keys()` regex (ENG-123, PROJ-1, AB-99999)
- Unit test sprint metric computations (velocity, completion, scope creep)
- Unit test developer auto-mapping by email
- Mock Linear GraphQL responses for sync integration tests
- Test graceful degradation when Linear is not configured (all existing features unchanged)

## Acceptance Criteria

### Phase 1 — Backend (Complete)
- [x] Linear API connection and authentication works
- [x] Teams, cycles, projects, and issues sync from Linear
- [x] PRs auto-linked to Linear issues via identifier matching
- [x] Developer identity mapping (auto by email + manual admin override)
- [x] Sprint velocity API with trend
- [x] Sprint completion rate (committed vs delivered)
- [x] Scope creep tracking per cycle
- [x] Triage latency metrics
- [x] Estimation accuracy trend
- [x] Work alignment (linked vs unlinked PRs)
- [x] Project health portfolio API
- [x] Planning ↔ delivery correlation insight
- [x] Integration config API (admin only, 11 endpoints)
- [x] Sprint/planning stats API (12 endpoints)
- [x] All existing features work without Linear configured (1010 tests pass)
- [x] Read-only — never writes to Linear
- [x] Encryption: Shared Fernet module extracted from slack.py

### Phase 2 — Frontend (Pending)
- [ ] Integration settings page (`/admin/integrations`)
- [ ] Sprint dashboard (`/insights/sprints`)
- [ ] Planning insights (`/insights/planning`)
- [ ] Project portfolio (`/insights/projects`)
- [ ] Dashboard integration (velocity sparkline, work alignment)

### Phase 3 — Advanced (Pending)
- [ ] Notification evaluators (sprint-at-risk, triage queue, scope creep)
- [ ] Benchmarks integration (planning metrics)
- [ ] AI analysis context (sprint data in 1:1 prep, team health)
- [ ] Linear webhooks (real-time sync)

## Implementation Notes

**Authentication:** API key only (not OAuth). Stored encrypted at rest via shared Fernet module (`services/encryption.py`). Same `ENCRYPTION_KEY` env var as Slack.

**Primary issue source toggle:** `is_primary_issue_source` flag on `integration_config`. Helper `get_primary_issue_source()` in `linear_sync.py` routes issue queries to `external_issues` (Linear) or `issues` (GitHub) table. Only one integration can be primary at a time.

**Sync scheduling:** Runs via APScheduler interval job (default 120 min). Uses `SyncEvent(sync_type="linear")` for tracking. Background sync uses its own `AsyncSessionLocal()` session (not request-scoped).

**PR linking:** `extract_linear_keys()` regex scans PR title, branch, and body for `[A-Z]{2,10}-\d+` patterns. Links stored in `pr_external_issue_links` with source attribution. Batched processing (500 PRs per batch).

**Developer mapping:** Auto-maps by email match during sync. Manual override via admin API. Mapping stored in `developer_identity_map` (one mapping per developer per integration type).

## Files Created

- `backend/app/services/encryption.py` — Shared Fernet encryption helpers (extracted from slack.py)
- `backend/app/services/linear_sync.py` — Linear GraphQL client, sync orchestration, PR linking, dev mapping
- `backend/app/services/sprint_stats.py` — Sprint velocity, completion, scope creep, triage, estimation, alignment, correlation
- `backend/app/api/integrations.py` — Integration config CRUD + sync trigger + user mapping (11 endpoints)
- `backend/app/api/sprints.py` — Sprint/planning/project stats (12 endpoints)
- `backend/migrations/versions/036_add_linear_integration_tables.py` — 6 new tables
- `backend/tests/unit/test_linear_sync.py` — 34 unit tests
- `backend/tests/unit/test_sprint_stats.py` — 6 unit tests
- `backend/tests/integration/test_integrations_api.py` — 10 integration tests
- `backend/tests/integration/test_sprints_api.py` — 15 integration tests

## Files Modified

- `backend/app/services/slack.py` — Imports encryption from shared module
- `backend/app/models/models.py` — 6 new model classes (~192 lines)
- `backend/app/schemas/schemas.py` — Integration + sprint schemas (~249 lines)
- `backend/app/config.py` — Added `linear_sync_interval_minutes`
- `backend/app/main.py` — 2 new routers, Linear sync scheduler job
