# DevPulse — Technical Specification

## 1. Overview

DevPulse is an engineering intelligence dashboard that tracks developer activity across all GitHub repositories in an organization. It provides quantitative metrics (PRs, reviews, cycle times) without AI by default, and offers on-demand AI analysis of communication patterns and team dynamics when explicitly triggered.

**Target user:** Engineering lead managing 20+ developers across 30+ GitHub repositories.

**Core principles:**
- AI is off by default. All stats are computed from raw data. AI analysis runs only when a user clicks a button.
- GitHub is the single source of truth. DevPulse reads from GitHub — it never writes back.
- Data is stored locally. GitHub API has rate limits; we cache everything in PostgreSQL and sync on a schedule.


## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                    React Frontend                    │
│  Dashboard │ Team Registry │ Stats │ AI Analysis     │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP/JSON
┌──────────────────────▼──────────────────────────────┐
│                   FastAPI Backend                     │
│                                                      │
│  ┌─────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ Team CRUD   │  │ Stats      │  │ AI Analysis  │  │
│  │ /developers │  │ /stats     │  │ /ai/analyze  │  │
│  └─────────────┘  └────────────┘  └──────┬───────┘  │
│                                          │ on-demand │
│  ┌─────────────────────────┐      ┌──────▼───────┐  │
│  │ GitHub Sync Service     │      │ Claude API   │  │
│  │ webhooks + nightly sync │      │ (Anthropic)  │  │
│  └────────┬────────────────┘      └──────────────┘  │
└───────────┼──────────────────────────────────────────┘
            │
  ┌─────────▼─────────┐    ┌────────────────┐
  │ GitHub REST API    │    │  PostgreSQL    │
  │ (GitHub App token) │    │  (all data)   │
  └───────────────────┘    └────────────────┘
```

**Tech stack:**
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic
- Database: PostgreSQL 15+
- Frontend: React 18+, TypeScript, Vite
- GitHub integration: REST API via httpx, GitHub App for auth
- AI: Anthropic Claude API (claude-sonnet-4-20250514), called on-demand only
- Scheduling: APScheduler (in-process) or system cron


## 3. Data Model

### 3.1 developers (Team Registry — auto-synced + manual data)

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| github_username | varchar(255) | UNIQUE, NOT NULL, indexed |
| display_name | varchar(255) | NOT NULL |
| email | varchar(255) | |
| role | varchar(50) | developer, senior_developer, lead, architect, devops, qa, intern |
| skills | jsonb | e.g. ["python", "react", "kubernetes"] |
| specialty | varchar(255) | frontend, backend, infra, fullstack, etc. |
| location | varchar(255) | "Oslo, Norway" |
| timezone | varchar(50) | "Europe/Oslo" (IANA format) |
| team | varchar(255) | "Platform", "Product", etc. |
| is_active | boolean | DEFAULT true |
| avatar_url | text | Synced from GitHub |
| notes | text | Free-text manager notes |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### 3.2 repositories

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| github_id | integer | UNIQUE, NOT NULL |
| name | varchar(255) | |
| full_name | varchar(512) | "org/repo", indexed |
| description | text | |
| language | varchar(100) | |
| is_tracked | boolean | DEFAULT true — allows excluding repos |
| last_synced_at | timestamptz | |
| created_at | timestamptz | |

### 3.3 pull_requests

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| github_id | integer | NOT NULL |
| repo_id | FK → repositories | NOT NULL |
| author_id | FK → developers | NULL if author not in team registry |
| number | integer | NOT NULL |
| title | text | |
| body | text | Stored for AI analysis |
| state | varchar(20) | open, closed |
| is_merged | boolean | |
| is_draft | boolean | |
| additions | integer | From GitHub PR stats (no per-commit fetch needed) |
| deletions | integer | |
| changed_files | integer | |
| comments_count | integer | |
| review_comments_count | integer | |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| merged_at | timestamptz | |
| closed_at | timestamptz | |
| first_review_at | timestamptz | Computed: earliest review submission time |
| time_to_first_review_s | integer | Computed: created_at → first_review_at |
| time_to_merge_s | integer | Computed: created_at → merged_at |
| html_url | text | |

**Constraints:** UNIQUE(repo_id, number). Index on (author_id, created_at).

### 3.4 pr_reviews

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| github_id | integer | UNIQUE, NOT NULL |
| pr_id | FK → pull_requests | NOT NULL |
| reviewer_id | FK → developers | NULL if reviewer not in team |
| state | varchar(30) | APPROVED, CHANGES_REQUESTED, COMMENTED, DISMISSED |
| body | text | Stored for AI analysis |
| submitted_at | timestamptz | |

### 3.5 issues

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| github_id | integer | NOT NULL |
| repo_id | FK → repositories | NOT NULL |
| assignee_id | FK → developers | NULL |
| number | integer | NOT NULL |
| title | text | |
| body | text | Stored for AI analysis |
| state | varchar(20) | open, closed |
| labels | jsonb | ["bug", "feature", ...] |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| closed_at | timestamptz | |
| time_to_close_s | integer | Computed: created_at → closed_at |
| html_url | text | |

**Constraints:** UNIQUE(repo_id, number).

### 3.6 issue_comments

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| github_id | integer | UNIQUE, NOT NULL |
| issue_id | FK → issues | NOT NULL |
| author_github_username | varchar(255) | Stored as username, not FK (may be external) |
| body | text | Stored for AI analysis |
| created_at | timestamptz | |

### 3.7 sync_events (operational log with resumability)

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| sync_type | varchar(30) | full, incremental |
| status | varchar(30) | started, completed, completed_with_errors, failed |
| repos_synced | integer | Count of repos successfully processed |
| prs_upserted | integer | |
| issues_upserted | integer | |
| errors | jsonb | List of structured error objects (see below) |
| started_at | timestamptz | |
| completed_at | timestamptz | |
| duration_s | integer | |
| repo_ids | jsonb | Specific repo IDs to sync (null = all tracked) |
| since_override | timestamptz | Custom "since" date override |
| total_repos | integer | Total repos in this sync run (for progress bar) |
| current_repo_name | varchar(512) | Currently syncing repo (null when idle/done) |
| repos_completed | jsonb | `[{repo_id, repo_name, status, prs, issues, warnings}]` |
| repos_failed | jsonb | `[{repo_id, repo_name, error}]` |
| is_resumable | boolean | True if sync can be resumed |
| resumed_from_id | integer FK | Points to the original interrupted sync event |
| log_summary | jsonb | Condensed log entries `[{ts, level, msg, repo?}]` (capped at 100) |
| rate_limit_wait_s | integer | Total seconds spent waiting for GitHub rate limits |

**Structured error objects:** Each entry in `errors` is `{repo, repo_id, step, error_type, status_code, message, retryable, timestamp, attempt}`. Errors classified as `github_api`, `auth`, `timeout`, or `unknown` with retryability flag.

**Sync resilience:** Commits after each repo completes (per-repo durability). Batch commits every 50 PRs within large repos. On crash, `is_resumable=True` and resume picks up remaining repos. Retry with exponential backoff (2s, 8s, 30s) for transient HTTP errors (502/503/504) and timeouts.

### 3.8 ai_analyses (on-demand results)

| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| analysis_type | varchar(50) | communication, conflict, sentiment, summary |
| scope_type | varchar(30) | developer, team, repo |
| scope_id | varchar(255) | ID or name of scoped entity |
| date_from | timestamptz | |
| date_to | timestamptz | |
| input_summary | text | Description of what data was sent to AI |
| result | jsonb | Structured AI output |
| raw_response | text | Full Claude response for debugging |
| model_used | varchar(100) | |
| tokens_used | integer | |
| triggered_by | varchar(255) | Who requested this |
| created_at | timestamptz | |

### Design decisions

- **No commits table.** Per-commit line stats require an individual API call per commit, which is a rate limit killer at scale. All code volume metrics (additions, deletions, changed_files) are tracked at the PR level, where GitHub provides them for free. If commit-level data is needed later, add it as a separate sync job with aggressive rate limiting.
- **Author resolution is soft but auto-creates.** PRs/issues/reviews store `author_id` as a nullable FK. During sync, `resolve_author()` auto-creates developers from embedded GitHub user data (login, avatar_url). Raw GitHub usernames are stored on `pull_requests.author_github_username`, `pr_reviews.reviewer_github_username`, and `issues.assignee_github_username` for efficient bulk backfill. Org members are synced via `GET /orgs/{org}/members` at the start of each sync and on-demand via `POST /sync/contributors`.
- **All text is stored.** PR bodies, review comments, and issue comments are persisted locally. This is the raw material for AI analysis, and avoids re-fetching from GitHub when analysis is triggered.


## 4. GitHub Integration

### 4.1 Authentication

Use a **GitHub App** installed on the organization. This provides:
- 15,000 requests/hour (vs 5,000 for a PAT)
- Org-scoped access (no personal account dependency)
- Fine-grained permissions (read-only for repos, issues, PRs)
- Webhook delivery with signature verification

**Required permissions (read-only):**
- Repository: Contents, Pull requests, Issues, Metadata
- Organization: Members (to sync avatars/profiles)

**Token flow:** On startup and before each sync, generate an installation access token from the App's private key + installation ID. Tokens expire after 1 hour; refresh before each sync run.

### 4.2 Sync Strategy

**Architecture:** `SyncContext` dataclass threads db session, HTTP client, sync event, and logger through the entire sync chain. Commits after each repo completes (per-repo durability) and every 50 PRs within large repos (batch commits). On crash, progress is preserved and sync is resumable.

**Nightly full sync (2:00 AM):**
1. Fetch all org repos via `GET /orgs/{org}/repos` (paginated, with retry)
2. For each tracked repo:
   - Proactive rate limit check before starting
   - Fetch all PRs via `GET /repos/{owner}/{repo}/pulls?state=all&sort=updated&direction=desc`
   - For each PR: fetch reviews, review comments, files, check runs
   - Fetch all issues (skip items with `pull_request` key) + issue comments
   - Sync repo tree and deployments (failures recorded as warnings, don't fail the repo)
   - **Commit** after repo completes — progress is durable
3. Set final status: `completed`, `completed_with_errors`, or `failed`. Log sync event with structured errors and log_summary.

**Incremental sync (every 15 minutes):**
- Same as full sync but filtered: only fetch items updated since `last_synced_at` on each repo.
- Use `since` parameter on issues/comments endpoints.
- Use `sort=updated&direction=desc` on PRs and stop pagination when you hit items older than `last_synced_at`.

**Resume:** When a sync fails or completes with errors, `is_resumable=True`. `POST /sync/resume/{id}` creates a new sync with only the remaining (non-completed) repos.

**Retry:** Transient HTTP errors (502/503/504) and timeouts are retried 3 times with exponential backoff (2s, 8s, 30s). Non-transient errors (401/403/404/422) fail immediately.

**Webhooks (real-time):**
- Events to subscribe to: `pull_request`, `pull_request_review`, `issues`, `issue_comment`
- Webhook endpoint: `POST /api/webhooks/github`
- Verify signature using `X-Hub-Signature-256` header and shared secret.
- On each event, upsert the relevant entity. For `pull_request` events, also re-fetch reviews.
- **Do NOT subscribe to `push` events** — we don't track individual commits.

**Deduplication:** All upserts use unique constraints (repo_id + number for PRs/issues, github_id for reviews/comments). Duplicate webhooks are handled naturally by the upsert logic.

### 4.3 Rate Limit Handling

- Check `X-RateLimit-Remaining` header on every response. Threshold: `< 200` remaining.
- Proactive `/rate_limit` API check before each repo — sleep proactively if low.
- If wait exceeds 5 minutes: commit current progress before sleeping (protects against process kill during wait).
- Track total rate limit wait time on `sync_event.rate_limit_wait_s` for visibility.
- The incremental sync should complete well within limits. The nightly full sync may take 20-40 minutes for 30 repos.

### 4.4 PR detail stats (additions/deletions)

The list PRs endpoint (`GET /repos/{owner}/{repo}/pulls`) does NOT return `additions`, `deletions`, or `changed_files`. These are only available on the individual PR endpoint (`GET /repos/{owner}/{repo}/pulls/{number}`).

**Strategy:** For each new or updated PR, make one additional API call to get the detail endpoint. This is acceptable because:
- New PRs trickle in via webhooks (1 extra call per PR event)
- The incremental sync only touches recently-updated PRs
- The nightly full sync can batch these with rate limit awareness

Cache the values — once a PR is merged/closed, its stats don't change.


## 5. API Endpoints

### 5.1 Team Registry

```
GET    /api/developers                  List all developers (filterable by team, active status)
POST   /api/developers                  Create developer (409 with reactivation info if inactive duplicate)
GET    /api/developers/{id}             Get single developer
PATCH  /api/developers/{id}             Update developer fields (including is_active toggle for deactivation/reactivation)
GET    /api/developers/{id}/deactivation-impact  Open PRs, issues, and branches before deactivation
DELETE /api/developers/{id}             Soft-delete (sets is_active=false)
```

#### Developer Deactivation

Deactivation soft-disables a developer by setting `is_active = false`. The developer is hidden from team views, workload, benchmarks, collaboration, and risk scoring. Their historical data (PRs, reviews, issues, goals) is preserved and viewable by ID. They cannot log in via OAuth while inactive.

Before deactivating, admins should check `GET /developers/{id}/deactivation-impact` which returns `open_prs`, `open_issues`, and `open_branches` (draft PRs excluded). This helps identify work that may need reassignment.

Reactivation is done via `PATCH /developers/{id}` with `{ is_active: true }`. Auto-reactivation also occurs during sync if the developer appears as a PR author, reviewer, issue assignee, or org member — a warning is logged for admin visibility.

Creating a developer whose `github_username` matches an inactive record returns a structured 409 (`{ code: "inactive_exists", developer_id, display_name }`) so the frontend can prompt for reactivation instead of showing a generic conflict error.

### 5.2 Stats (no AI)

```
GET    /api/stats/developer/{id}        Developer stats for a date range
GET    /api/stats/team                  Aggregated team stats (filterable by team name)
GET    /api/stats/repo/{id}             Per-repo stats with top contributors
```

All stats endpoints accept `?date_from=...&date_to=...` query params. Default: last 30 days.

**Developer stats response includes:**
- PRs opened / merged / closed-without-merge / currently open
- Total additions / deletions / changed files (from PRs)
- Reviews given (approved / changes_requested / commented)
- Reviews received
- Avg time to first review (hours)
- Avg time to merge (hours)
- Issues assigned / closed
- Avg time to close issue (hours)

### 5.3 Sync Control

```
POST   /api/sync/start                  Start configurable sync (accepts SyncTriggerRequest)
POST   /api/sync/resume/{event_id}      Resume an interrupted sync (remaining repos only)
POST   /api/sync/contributors           Sync org members + backfill author links (background task)
GET    /api/sync/status                 Get active sync progress + summary stats
GET    /api/sync/repos                  List all repos with tracking status + PR/issue counts
PATCH  /api/sync/repos/{id}/track       Enable/disable tracking for a repo
GET    /api/sync/events                 List recent sync events with full progress details
```

**Concurrency guard:** Returns `409 Conflict` if a sync is already running. Scheduler jobs also skip if an active sync exists.

### 5.4 Webhooks

```
POST   /api/webhooks/github             GitHub webhook receiver (signature-verified)
```

### 5.5 AI Analysis (on-demand only)

```
POST   /api/ai/analyze                  Trigger an analysis (requires explicit user action)
GET    /api/ai/history                  List past analysis results
GET    /api/ai/history/{id}             Get a specific analysis result
```

**POST /api/ai/analyze request body:**
```json
{
  "analysis_type": "communication | conflict | sentiment",
  "scope_type": "developer | team | repo",
  "scope_id": "123",
  "date_from": "2026-03-01T00:00:00Z",
  "date_to": "2026-03-28T00:00:00Z"
}
```

### 5.6 Authentication

**Implemented:** GitHub OAuth with JWT sessions and role-based access control.

**Auth flow:**
1. User clicks "Login with GitHub" → frontend calls `GET /api/auth/login` → receives GitHub OAuth authorize URL
2. User authorizes on GitHub → redirected to `GET /api/auth/callback?code=...`
3. Backend exchanges code for GitHub access token, fetches GitHub user profile
4. Backend looks up or creates developer by `github_username`, issues a signed JWT (7-day expiry)
5. Backend redirects to frontend with JWT → frontend stores in `localStorage`
6. All subsequent API calls include `Authorization: Bearer {jwt}`

**Roles:**
- `admin` — full access to all endpoints (manage developers, view all stats, sync, AI analysis)
- `developer` — read-only access to own stats, profile, goals, and repo stats

**Bootstrap:** Set `DEVPULSE_INITIAL_ADMIN` env var to a GitHub username. That user is auto-promoted to `admin` on first OAuth login. Subsequently, admins can promote other users via `PATCH /api/developers/{id}` with `app_role: "admin"`.

**Access control:** Endpoints use per-route dependency injection — `get_current_user()` returns `AuthUser(developer_id, github_username, app_role)`, `require_admin()` raises `403 Forbidden` for non-admin users. Public endpoints: `/api/health`, `/api/webhooks/github`, `/api/auth/*`.

**Environment variables:**
- `GITHUB_CLIENT_ID` — GitHub OAuth client ID (from GitHub App settings)
- `GITHUB_CLIENT_SECRET` — GitHub OAuth client secret
- `JWT_SECRET` — secret for signing JWT tokens (min 32 chars recommended)
- `DEVPULSE_INITIAL_ADMIN` — GitHub username auto-promoted to admin on first login (optional)
- `FRONTEND_URL` — frontend URL for OAuth redirect (default: `http://localhost:5173`)


## 6. AI Analysis Module

### 6.1 Design Principles

- Never runs automatically. Every analysis is triggered by an explicit API call (which maps to a button click in the UI).
- All AI input comes from locally stored data. No live GitHub API calls during analysis.
- Results are stored in `ai_analyses` table for history and auditing.
- Token usage is tracked per analysis.

### 6.2 Analysis Types

**communication** (scope: developer)
Analyzes a developer's PR descriptions, review comments, and issue comments for:
- Clarity of PR descriptions
- Constructiveness of review feedback
- Responsiveness and engagement
- Overall communication tone
- Output: scores (1-10) + qualitative observations + recommendations

**conflict** (scope: team)
Analyzes team-wide interactions, focusing on:
- `CHANGES_REQUESTED` reviews (but not limited to — also scans regular comments)
- Recurring friction patterns between specific reviewer-author pairs
- Whether feedback is constructive or potentially demotivating
- Systemic process issues vs. individual issues
- Output: conflict score + friction pairs + recurring issues + recommendations

**sentiment** (scope: developer | team | repo)
Lighter analysis of overall tone and morale across comments and PR descriptions.
- Output: sentiment score + trend + notable patterns

### 6.3 Data Preparation

Before sending to Claude, the service:
1. Queries the relevant text data from the DB (PR bodies, review bodies, issue comments) filtered by scope and date range.
2. Truncates individual items to 500 chars to fit context windows.
3. Limits to most recent 50 items per category.
4. Assembles into a structured prompt with clear sections.
5. Stores a summary of what was sent (`input_summary` field) for auditing.

### 6.4 Prompt Strategy

Use Claude's structured output capability. System prompt instructs the model to respond in JSON with a defined schema. Parse with fallback handling (strip markdown fences, handle partial JSON).

**Future improvement:** Use tool_use/function calling for guaranteed structured output instead of JSON-in-text parsing.


## 7. Frontend

### 7.1 Pages

**Dashboard (home)**
- Team overview: active developer count, total PRs this period, merge rate, avg time to review
- Sparkline trends for key metrics over last 4 weeks
- Recent activity feed (latest PRs merged, issues closed)

**Team Registry**
- Table of all developers with role, team, skills, location, timezone
- Add/edit developer modal
- Click row → developer detail page

**Developer Detail**
- Profile card (name, role, skills, timezone)
- Stats panel for selected date range
- PR list (sortable, filterable by state)
- Review activity (given + received)
- "Run AI Analysis" button (opens modal to configure and trigger)
- Past AI analysis results (collapsible cards)

**Repos**
- List of all synced repos with tracking toggle
- Per-repo stats on click
- Last synced timestamp

**Sync Status**
- Current sync state
- Sync event log (recent runs with status, duration, error count)
- Manual sync trigger buttons

**AI Analysis**
- Analysis history table
- Trigger new analysis form (select type, scope, date range)
- Result viewer (structured display of JSON results)

### 7.2 State Management

Use React Query (TanStack Query) for server state. No complex client state needed — this is a read-heavy dashboard.

### 7.3 Date Range

Global date range picker in the top nav. All stats endpoints respect it. Default: last 30 days.


## 8. Configuration

All configuration via environment variables:

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/devpulse

# GitHub App
GITHUB_APP_ID=12345
GITHUB_APP_PRIVATE_KEY_PATH=./github-app.pem
GITHUB_APP_INSTALLATION_ID=67890
GITHUB_WEBHOOK_SECRET=whsec_...
GITHUB_ORG=your-org-name

# Auth (Phase 1)
DEVPULSE_ADMIN_TOKEN=some-secure-random-string

# AI (optional — only needed if you want AI analysis)
ANTHROPIC_API_KEY=sk-ant-...

# Sync
SYNC_INTERVAL_MINUTES=15
FULL_SYNC_CRON_HOUR=2
```


## 9. Project Structure

```
devpulse/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, middleware
│   │   ├── config.py                # pydantic-settings config
│   │   ├── api/
│   │   │   ├── developers.py        # Team registry CRUD
│   │   │   ├── stats.py             # Stats endpoints
│   │   │   ├── ai_analysis.py       # AI trigger + history
│   │   │   ├── sync.py              # Sync control + repo management
│   │   │   └── webhooks.py          # GitHub webhook handler
│   │   ├── models/
│   │   │   ├── models.py            # SQLAlchemy models
│   │   │   └── database.py          # Engine + session factory
│   │   ├── services/
│   │   │   ├── github_sync.py       # Sync logic (full, incremental, webhook)
│   │   │   ├── stats.py             # Stats computation (pure SQL)
│   │   │   └── ai_analysis.py       # Claude API integration
│   │   └── schemas/
│   │       └── schemas.py           # Pydantic request/response models
│   ├── migrations/                   # Alembic migrations
│   ├── requirements.txt
│   └── alembic.ini
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── TeamRegistry.tsx
│   │   │   ├── DeveloperDetail.tsx
│   │   │   ├── Repos.tsx
│   │   │   ├── SyncStatus.tsx
│   │   │   └── AIAnalysis.tsx
│   │   ├── components/              # Shared UI components
│   │   ├── hooks/                   # React Query hooks for each API
│   │   └── utils/                   # API client, formatters
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml               # PostgreSQL + backend + frontend
├── CLAUDE.md                        # Project context for Claude Code
└── README.md
```


## 10. Implementation Order

**Phase 1 — Data foundation (week 1-2)**
1. Set up project scaffolding (FastAPI, Alembic, PostgreSQL via Docker)
2. Implement data models + migrations
3. Build GitHub App, register webhook
4. Implement sync service (full sync first, then incremental)
5. Test sync against 2-3 real repos
6. Add sync_events logging

**Phase 2 — Stats + API (week 2-3)**
7. Implement stats service
8. Build all API endpoints
9. Add bearer token auth middleware
10. Test all endpoints with real synced data

**Phase 3 — Frontend (week 3-4)**
11. Scaffold React app with routing
12. Build Dashboard + Team Registry pages
13. Build Developer Detail + Stats views
14. Add date range picker, connect to stats API
15. Build Sync Status + Repo management page

**Phase 4 — AI analysis (week 4-5)**
16. Implement AI analysis service with communication + conflict types
17. Build AI Analysis page in frontend
18. Add "Run Analysis" button on Developer Detail page
19. Iterate on prompts with real data

**Phase 5 — Hardening**
20. Add webhook deduplication logging
21. Rate limit awareness in sync service
22. Error handling + retry logic
23. Azure AD SSO (if needed)


## 11. Open Questions

1. **Should external contributors (not in team registry) show up in stats?** Current design: their PRs/reviews are stored but not queryable by developer. Could add an "external" flag instead.

2. ~~**Do you want Slack/Teams notifications** when AI analysis detects something notable?~~ **Implemented.** Slack integration added with 6 notification types (stale PRs, high-risk PRs, workload alerts, sync status, weekly digest). Bot token approach with per-user DM delivery. See `backend/app/services/slack.py` and `/admin/slack` settings page.

3. **Multi-org support?** Current design assumes one org. If you need multiple orgs later, add an `org_id` column to repositories.

4. **Data retention policy?** After 12 months of data, the issues/comments tables could get large. Worth defining a retention window or archival strategy.
