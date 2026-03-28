# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

DevPulse — an engineering intelligence dashboard that tracks developer activity across GitHub repositories for an organization. Provides PR/review/cycle-time metrics, team benchmarks, trend analysis, workload balance, collaboration insights, developer goals, and optional on-demand AI analysis via Claude API.

**Core invariants:**
- AI is off by default; all stats are computed deterministically from raw data
- GitHub is the single source of truth; DevPulse is read-only (never writes back to GitHub)
- All GitHub data is cached locally in PostgreSQL to handle rate limits
- All backend I/O is async (SQLAlchemy async sessions, httpx.AsyncClient)

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async with asyncpg), Alembic migrations
- **Database:** PostgreSQL 15+ (async via asyncpg)
- **Frontend:** React 19, TypeScript, Vite, Tailwind CSS v4, shadcn/ui (base-nova style), TanStack Query v5, pnpm
- **GitHub integration:** REST API via httpx, GitHub App auth (JWT + installation tokens)
- **AI:** Anthropic Claude API (claude-sonnet-4-0), on-demand only
- **Scheduling:** APScheduler AsyncIOScheduler (in-process, configured in FastAPI lifespan)
- **Testing:** pytest + pytest-asyncio (backend), aiosqlite for in-memory test DB

## Architecture

```
React Frontend (Vite :5173)  ──/api proxy──>  FastAPI Backend (:8000)  ──>  PostgreSQL (:5432)
                                                     ↕
                                              GitHub REST API (read-only)
                                                     ↕
                                              Claude API (on-demand AI analysis)
```

### Data Flow

1. **GitHub App** authenticates via JWT → installation token (cached, auto-refreshed)
2. **Scheduled sync** (APScheduler) fetches repos → PRs → reviews → review comments → issues → issue comments
3. **Webhooks** provide real-time updates for PR/review/issue events
4. **Stats service** computes metrics on-demand from cached data (no materialized views)
5. **AI analysis** gathers context from stats/collaboration/goals, sends to Claude, stores structured result

### Backend Layout

```
backend/app/
├── api/              # FastAPI routers (thin delegation to services)
│   ├── auth.py       # HTTPBearer token validation
│   ├── developers.py # Team registry CRUD
│   ├── stats.py      # Stats, benchmarks, trends, workload, collaboration endpoints
│   ├── goals.py      # Developer goals CRUD + progress
│   ├── sync.py       # Sync trigger/status endpoints
│   ├── webhooks.py   # GitHub webhook receiver (HMAC-verified)
│   └── ai_analysis.py # AI analysis + 1:1 prep + team health endpoints
├── models/
│   ├── database.py   # Async engine, session factory, Base, get_db() dependency
│   └── models.py     # All 10 SQLAlchemy ORM models
├── schemas/
│   └── schemas.py    # All Pydantic request/response models and enums
├── services/
│   ├── github_sync.py    # GitHub App auth, rate limiting, upsert helpers, sync orchestration
│   ├── stats.py          # All metrics: developer, team, repo, benchmarks, trends, workload
│   ├── collaboration.py  # Collaboration matrix + insights (silos, bus factors, isolation)
│   ├── goals.py          # Goal CRUD, metric computation, auto-achievement
│   └── ai_analysis.py    # Claude API integration, 1:1 prep briefs, team health checks
├── config.py         # pydantic-settings: all env vars
└── main.py           # FastAPI app factory, CORS, router registration, APScheduler
```

### Frontend Layout

```
frontend/src/
├── pages/            # Route components (Dashboard, TeamRegistry, DeveloperDetail, Repos, SyncStatus, AIAnalysis)
├── components/
│   ├── Layout.tsx    # Sticky header, nav, global date range picker
│   ├── StatCard.tsx  # Reusable stat display card
│   └── ui/           # shadcn/ui primitives (button, card, table, dialog, select, etc.)
├── hooks/            # TanStack Query hooks (useDevelopers, useStats, useSync, useAI, useDateRange)
├── utils/
│   ├── api.ts        # apiFetch<T>() wrapper with Bearer auth from localStorage
│   └── types.ts      # TypeScript interfaces mirroring backend schemas
└── lib/utils.ts      # cn() utility (clsx + tailwind-merge)
```

**Import alias:** `@/` maps to `src/` (configured in vite.config.ts and tsconfig).

## Database Schema (10 tables)

| Table | Purpose | Key Relationships |
|-------|---------|-------------------|
| `developers` | Team registry with GitHub username, role, team, skills | Has many: pull_requests, reviews, issues, goals |
| `repositories` | GitHub repos with tracking toggle | Has many: pull_requests, issues |
| `pull_requests` | PRs with pre-computed cycle times | Belongs to: repo, author. Has many: reviews, review_comments |
| `pr_reviews` | Reviews with quality tier classification | Belongs to: pr, reviewer. Has many: comments |
| `pr_review_comments` | Inline code review comments | Belongs to: pr, review |
| `issues` | Issues with close-time computation | Belongs to: repo, assignee. Has many: comments |
| `issue_comments` | Issue comment bodies | Belongs to: issue |
| `sync_events` | Sync run audit log | Standalone |
| `ai_analyses` | AI analysis results (JSONB) | Standalone (scope_type + scope_id reference other tables) |
| `developer_goals` | Goal tracking with metric targets | Belongs to: developer |

**Key design decisions:**
- Author/reviewer FKs are **nullable** — external contributors not in the team registry get `NULL`
- Cycle-time fields (`time_to_first_review_s`, `time_to_merge_s`, `time_to_close_s`) are pre-computed at sync time
- `pr_reviews.quality_tier` is computed deterministically: `thorough` (>500 chars or 3+ inline comments), `standard` (100-500 chars), `rubber_stamp` (APPROVED + <20 chars), `minimal` (default)
- JSONB columns: `skills`, `labels`, `errors`, `result` (AI analysis output)
- No commit-level data — stats are PR-level only to stay within GitHub rate limits

## GitHub Integration

### GitHub App Setup

**Required permissions (all read-only):**
- Repository: Contents, Pull requests, Issues, Metadata
- Organization: Members

**Webhook events to subscribe:**
- `pull_request` — PR created/updated/merged/closed
- `pull_request_review` — review submitted
- `pull_request_review_comment` — inline code comment added/edited
- `issues` — issue created/updated/closed
- `issue_comment` — issue comment added (PR comments are skipped via `pull_request` key detection)

**Do NOT subscribe to:** `push` (commits are not tracked)

### Authentication Flow

1. `GitHubAuth` generates a 10-minute RS256 JWT signed with the app's private key
2. JWT is exchanged for an installation token via `POST /app/installations/{id}/access_tokens`
3. Installation token is cached and auto-refreshed 60 seconds before expiry
4. All GitHub API calls use `Authorization: Bearer {installation_token}`

### Webhook Verification

`verify_signature()` computes HMAC-SHA256 of raw request body using `GITHUB_WEBHOOK_SECRET`, then constant-time compares against `X-Hub-Signature-256` header.

### Sync Strategy

| Mode | Schedule | Scope | Mechanism |
|------|----------|-------|-----------|
| **Full sync** | Cron at `FULL_SYNC_CRON_HOUR` (default 2 AM) | All tracked repos, all PRs/issues | `run_sync("full")` |
| **Incremental sync** | Every `SYNC_INTERVAL_MINUTES` (default 15) | Changed since `last_synced_at` | `run_sync("incremental")` with `stop_before` pagination |
| **Webhook** | Real-time | Single event | `POST /api/webhooks/github` |

**Sync flow per repo:** fetch PRs → for each PR: upsert PR + fetch reviews + fetch review comments + recompute quality tiers → fetch issues → fetch issue comments → update `repo.last_synced_at`

**Rate limit handling:** checks `X-RateLimit-Remaining` header; sleeps until reset when < 100 remaining.

## API Structure

All endpoints except `/api/health` and `/api/webhooks/github` require `Authorization: Bearer {DEVPULSE_ADMIN_TOKEN}`.

### Core Endpoints

| Group | Endpoints |
|-------|-----------|
| **Health** | `GET /api/health` |
| **Developers** | `GET/POST /api/developers`, `GET/PATCH/DELETE /api/developers/{id}` |
| **Stats** | `GET /api/stats/developer/{id}`, `GET /api/stats/team`, `GET /api/stats/repo/{id}` |
| **Sync** | `POST /api/sync/full`, `POST /api/sync/incremental`, `GET /api/sync/repos`, `PATCH /api/sync/repos/{id}/track`, `GET /api/sync/events` |
| **Webhooks** | `POST /api/webhooks/github` |
| **AI** | `POST /api/ai/analyze`, `GET /api/ai/history`, `GET /api/ai/history/{id}` |

### Management Feature Endpoints (M1-M8)

| Feature | Endpoint | Description |
|---------|----------|-------------|
| **M1: Review Quality** | `GET /api/stats/developer/{id}` | `review_quality_breakdown` + `review_quality_score` in response |
| **M2: Benchmarks** | `GET /api/stats/benchmarks` | p25/p50/p75 percentiles across team |
| **M2: Percentiles** | `GET /api/stats/developer/{id}?include_percentiles=true` | Developer stats with team-relative percentile placement |
| **M3: Trends** | `GET /api/stats/developer/{id}/trends` | Period-bucketed stats with linear regression |
| **M4: Workload** | `GET /api/stats/workload` | Per-developer load indicators + automated alerts |
| **M5: Collaboration** | `GET /api/stats/collaboration` | Reviewer-author matrix + insights (silos, bus factors) |
| **M6: Goals** | `POST/GET /api/goals`, `PATCH /api/goals/{id}`, `GET /api/goals/{id}/progress` | Developer goal CRUD with auto-achievement |
| **M7: 1:1 Prep** | `POST /api/ai/one-on-one-prep` | AI-generated structured 1:1 meeting brief |
| **M8: Team Health** | `POST /api/ai/team-health` | AI-generated comprehensive team health assessment |

See `docs/API.md` for full request/response contracts.

## Environment Variables

Defined in `backend/app/config.py` via pydantic-settings. Copy `.env.example` to `.env`.

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://devpulse:devpulse@localhost:5432/devpulse` | Async PostgreSQL connection |
| `GITHUB_APP_ID` | Yes | `0` | GitHub App numeric ID |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Yes | `./github-app.pem` | Path to GitHub App RSA private key |
| `GITHUB_APP_INSTALLATION_ID` | Yes | `0` | GitHub App installation ID for the org |
| `GITHUB_WEBHOOK_SECRET` | Yes | `""` | HMAC secret for webhook signature verification |
| `GITHUB_ORG` | Yes | `""` | GitHub organization name (e.g. `my-company`) |
| `DEVPULSE_ADMIN_TOKEN` | Yes | `""` | Bearer token for API authentication |
| `ANTHROPIC_API_KEY` | For AI | `""` | Anthropic API key (only needed for AI features) |
| `SYNC_INTERVAL_MINUTES` | No | `15` | Incremental sync interval |
| `FULL_SYNC_CRON_HOUR` | No | `2` | Hour (UTC) for nightly full sync |

## Running

### Docker (recommended)

```bash
cp .env.example .env   # edit with your values — see env vars table above
docker compose up
```

| Service | URL | Notes |
|---------|-----|-------|
| Backend | http://localhost:8000 | FastAPI with auto-reload |
| Frontend | http://localhost:5173 | Vite dev server, proxies /api to backend |
| Database | localhost:5432 | PostgreSQL 15, user/pass/db: `devpulse` |

### Local development

```bash
# Backend
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
pnpm install
pnpm dev
```

### Database migrations

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Running tests

```bash
cd backend
pip install -r requirements-test.txt
python -m pytest                    # all tests
python -m pytest tests/unit/        # unit tests only
```

Tests use SQLite in-memory via aiosqlite (no PostgreSQL needed for testing).

## Key Patterns and Conventions

### Backend patterns
- **Thin API routes:** Routes validate input and delegate to service functions — no business logic in routes
- **Service functions:** All async, accept `AsyncSession` as first param, return Pydantic models or ORM objects
- **Upsert pattern:** SELECT by unique key → create if not found → always overwrite mutable fields (idempotent)
- **Date range defaulting:** `_default_range()` helper — defaults to last 30 days if params are None
- **Review quality tiers:** Computed at sync time by `classify_review_quality()` (pure function), then recomputed after review comments are synced via `recompute_review_quality_tiers()`
- **Percentile band inversion:** For lower-is-better metrics (time_to_merge, time_to_first_review, review_turnaround), `_percentile_band()` inverts labels so `above_p75` always means "best"
- **Trend regression:** Simple OLS `_linear_regression()` with polarity-aware direction classification; <5% change = "stable"
- **Goal auto-achievement:** Checked on progress fetch — if metric crosses target for 2 consecutive weekly periods, auto-marks as achieved
- **AI analysis:** Data gathering → structured system prompt → Claude API call → JSON parse → store in `ai_analyses`

### Frontend patterns
- **Global date range:** React Context (`DateRangeContext`) set in Layout header, consumed by all pages
- **Server state:** TanStack Query with 30s stale time, 1 retry
- **Auth:** Bearer token from `localStorage` key `devpulse_token`, injected by `apiFetch()` wrapper
- **API proxy:** Vite dev server proxies `/api/*` → `http://localhost:8000`
- **Component library:** shadcn/ui with base-nova style, neutral base color, CSS variables, Lucide icons

## Specification

- `DEVPULSE_SPEC.md` — Full technical specification (data models, API contracts, sync logic, implementation phases)
- `DEVPULSE_MANAGEMENT_FEATURES.md` — Management features spec (M1-M8: review quality, benchmarks, trends, workload, collaboration, goals, AI briefs)
- `docs/API.md` — Complete API reference with all endpoints, request/response schemas

## Task System

Task files live in `.claude/tasks/` (core spec) and `.claude/tasks/management-improvements/` (M1-M8).

**All tasks are completed:**
- Core: 01-12 (project scaffolding through frontend pages)
- Management Phase 1: M1 (review quality), M2 (benchmarks), M3 (trends), M4 (workload)
- Management Phase 2: M5 (collaboration matrix), M6 (developer goals)
- Management Phase 3: M7 (1:1 prep brief), M8 (team health check)
